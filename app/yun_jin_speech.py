# SPDX-License-Identifier: GPL-3.0-or-later
"""Qt speech controller: no GUI blocking, no automatic provider switching."""
import json
import bisect
import sys
import time
from pathlib import Path
from PyQt6.QtCore import QObject, QProcess, QTimer, QUrl, pyqtSignal
from yun_jin_core import BASE
from yun_jin_platform import action_label

VOICES={
    'it':[('Elsa · italiano','it-IT-ElsaNeural'),('Isabella · italiano','it-IT-IsabellaNeural')],
    'en':[('Sonia · inglese UK','en-GB-SoniaNeural'),('Jenny · inglese USA','en-US-JennyNeural')],
    'zh-CN':[('Xiaoxiao · mandarino','zh-CN-XiaoxiaoNeural'),('Xiaoyi · mandarino','zh-CN-XiaoyiNeural')],
}


def caption_pages(text):
    """Small readable chunks, including languages without spaces; no text is lost."""
    text = ' '.join(text.split())
    limit = 72 if any('\u3400' <= c <= '\u9fff' for c in text) else 140
    pages = []
    while len(text) > limit:
        boundary = max(text.rfind(c, limit//2, limit+1) for c in ' .!?;。！？；')
        end = boundary+1 if boundary >= 0 else limit
        pages.append(text[:end].strip()); text = text[end:].lstrip()
    if text: pages.append(text)
    return pages


class Speech(QObject):
    status_changed=pyqtSignal(str)
    active_changed=pyqtSignal(bool)
    caption_changed=pyqtSignal(str)

    def __init__(self,pet):
        super().__init__(pet)
        self.pet=pet
        # Migrate the two old switches to one automatic-reading preference.
        # A previous opt-out must never enable unsolicited speech on update.
        if self.pref('auto_reminders',None) is None:
            self.pet.store.set_preference('tts_auto_reminders',bool(self.pref('enabled',True) and self.pref('reminders',True)))
        self.process=None
        self.player=None
        self.output=None
        self.player_attempted=False
        self.busy=False
        self.closed=False
        self.current_tag=None
        self.category='manual'
        self.status=''
        self.current_text=''
        self.caption_pages=[]
        self.caption_ends=[]
        self.caption_index=-1
        self.caption_playing=False
        self.cache=pet.store.root/'voice-cache'
        self.cache.mkdir(exist_ok=True)
        self.timeout=QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self.timed_out)
        self.cached_timer=QTimer(self)
        self.cached_timer.setSingleShot(True)
        self.cached_timer.timeout.connect(self.play_cached)
        self.cached_path=None

    def ensure_player(self):
        if self.player is not None and self.output is not None:return True
        if self.player_attempted:return False
        self.player_attempted=True
        try:
            from PyQt6.QtMultimedia import QMediaPlayer,QAudioOutput
            self.player=QMediaPlayer(self)
            self.output=QAudioOutput(self)
            self.player.setAudioOutput(self.output)
            self.player.playbackStateChanged.connect(self.playback_state)
            self.player.positionChanged.connect(self.update_caption)
            self.player.durationChanged.connect(lambda _: self.update_caption())
            self.player.mediaStatusChanged.connect(self.media_status)
            self.player.errorOccurred.connect(self.playback_error)
        except Exception as exc:
            self.status='Riproduzione vocale non disponibile: '+str(exc)
            if self.player is not None:self.player.deleteLater();self.player=None
            if self.output is not None:self.output.deleteLater();self.output=None
        return self.player is not None and self.output is not None

    def pref(self,key,default):
        return self.pet.store.preference('tts_'+key,default)

    def set_pref(self,key,value):
        self.pet.store.set_preference('tts_'+key,value)
        if key=='auto_reminders' and not value and self.category=='reminder':
            self.stop()
        if key=='volume' and self.output:
            self.output.setVolume(value/100)

    def report(self,text):
        if self.category == 'ambient':
            return
        self.status=text
        self.status_changed.emit(text)

    def ambient_allowed(self, tag=None):
        context = getattr(self.pet, 'context', None)
        tag = tag or self.current_tag or {}
        return bool(context and context.enabled.get(tag.get('kind'), False)
                    and time.time() >= self.pet.sound.quiet_until
                    and int(self.pref('volume', 70)) > 0
                    and context.can_react(ignore_speech=True, serial=tag.get('serial')))

    def animate_ambient(self):
        context = getattr(self.pet, 'context', None)
        if self.category == 'ambient' and self.current_tag and context:
            context.play_speech_animation(self.current_tag)

    def speak(self,text,category='manual',tag=None,preview=False,language=None):
        if category == 'ambient':
            if self.busy or not self.ambient_allowed(tag):
                return False
        elif self.category == 'ambient':
            # User actions and reminders always take precedence over ambient speech.
            self.stop(announce=False)
            self.category = category
        text=str(text).strip()
        if not text:
            self.report('Nessun testo da leggere.')
            return False
        if len(text)>3000:
            self.report('Massimo 3000 caratteri. Seleziona un passaggio.')
            return False
        if not preview and time.time()<self.pet.sound.quiet_until:
            self.report('Silenzio attivo. Riattiva i suoni dal menu.')
            return False
        if category=='reminder' and (self.busy or (getattr(self.pet,'metronome',None) and self.pet.metronome.running) or not self.pref('auto_reminders',True)):
            return False
        if not self.ensure_player():
            self.report('Qt Multimedia non è disponibile: reinstalla le dipendenze.')
            return False
        self.stop(announce=False)
        self.category=category
        self.current_tag=tag
        self.busy=True
        self.current_text=text
        self.caption_pages=caption_pages(text)
        total=0
        for page in self.caption_pages:
            total += len(page)
            self.caption_ends.append(total)
        language=language or self.pref('language','it')
        provider=self.pref('provider','edge')
        default_voice=VOICES.get(language,VOICES['it'])[0][1]
        voice=self.pref('voice_'+language,default_voice)
        job={'text':text,'provider':provider,'voice':voice,'language':language,
             'rate':(int(self.pref('rate',20)) if provider=='edge' else (-1 if self.pref('google_slow',0) else 0)),
             'pitch':(int(self.pref('pitch',15)) if provider=='edge' else 0),
             'cache':str(self.cache)}
        # Reuse the worker's key, but do not start an interpreter for local audio.
        from yun_jin_tts_worker import cache_key
        cached=self.cache/(cache_key(job)+'.mp3')
        try:
            usable=cached.is_file() and cached.stat().st_size>128
        except OSError:
            usable=False
        if usable:
            self.cached_path=cached
            self.cached_timer.start(0)
            self.report('Preparazione…')
            return True
        process=QProcess(self)
        self.process=process
        executable=Path(sys.executable)
        if sys.platform=='win32' and executable.name.lower()=='pythonw.exe':
            console_python=executable.with_name('python.exe')
            if console_python.is_file():
                executable=console_python
        process.setProgram(str(executable))
        process.setArguments([str(BASE/'yun_jin_tts_worker.py')])
        process.finished.connect(lambda code,status,p=process:self.generated(p,code))
        process.errorOccurred.connect(lambda error,p=process:self.process_error(p,error))
        process.started.connect(lambda p=process,j=job:self.write_job(p,j))
        process.start()
        self.timeout.start(12000 if category == 'ambient' else 45000)
        self.report('Preparazione…')
        return True

    def write_job(self,process,job):
        if process is self.process:
            process.write(json.dumps(job,ensure_ascii=False).encode('utf-8'))
            process.closeWriteChannel()

    def process_error(self,process,error):
        if process is not self.process:
            return
        if error==QProcess.ProcessError.FailedToStart:
            self.timeout.stop()
            self.process=None
            self.animate_ambient()
            self.busy=False
            process.deleteLater()
            self.report('Impossibile avviare il generatore vocale. Verifica il Python usato dal collegamento.')

    def generated(self,process,code):
        if process is not self.process:
            process.deleteLater()
            return
        self.process=None
        self.timeout.stop()
        raw=bytes(process.readAllStandardOutput())
        process.deleteLater()
        try:
            reply=json.loads(raw.decode('utf-8'))
            if code!=0 or not reply.get('ok'):
                raise ValueError(reply.get('error','Il servizio non ha restituito una risposta.'))
        except Exception as exc:
            self.audio_error(exc)
            return
        self.play_file(reply.get('path',''))

    def play_cached(self):
        path,self.cached_path=self.cached_path,None
        if self.closed or not self.busy or path is None:return
        self.play_file(path,refresh=True)

    def play_file(self,path,refresh=False):
        try:
            path=Path(path).resolve()
            path.relative_to(self.cache.resolve())
            if not path.is_file() or path.suffix!='.mp3':
                raise ValueError('File vocale non valido.')
            if refresh:path.touch()
            if self.category=='reminder' and self.current_tag:
                active={r['id'] for r in self.pet.store.reminders()}
                if self.current_tag not in active:
                    self.busy=False
                    return
            if self.category == 'ambient' and not self.ambient_allowed():
                self.busy=False
                self.current_tag=None
                return
            self.output.setVolume(max(0,min(100,int(self.pref('volume',70))))/100)
            self.player.setSource(QUrl.fromLocalFile(str(path)))
            self.player.play()
            self.report('Lettura…')
        except Exception as exc:
            self.audio_error(exc)

    def audio_error(self,exc):
        self.animate_ambient()
        self.busy=False
        self.current_tag=None
        self.report('Voce non disponibile: '+str(exc)+' Riprova o cambia servizio.')

    def clear_caption(self):
        if self.caption_index != -1:
            self.caption_index=-1
            self.caption_changed.emit('')
        self.caption_playing=False

    def update_caption(self, position=None):
        if not self.caption_playing or not self.caption_pages or not self.player:
            return
        duration=self.player.duration()
        position=self.player.position() if position is None else position
        progress=max(0, position)/duration if duration > 0 else 0
        index=min(len(self.caption_pages)-1,
                  bisect.bisect_right(self.caption_ends, progress*self.caption_ends[-1]))
        if index != self.caption_index:
            self.caption_index=index
            self.caption_changed.emit(self.caption_pages[index])

    def playback_state(self,state):
        from PyQt6.QtMultimedia import QMediaPlayer
        playing=state==QMediaPlayer.PlaybackState.PlayingState
        if playing and self.busy and self.category == 'ambient' and not self.ambient_allowed():
            self.stop(announce=False)
            return
        self.caption_playing=playing and self.busy
        if self.caption_playing:
            self.animate_ambient()
            self.update_caption()
        else:
            self.clear_caption()
        self.active_changed.emit(playing)

    def media_status(self,status):
        from PyQt6.QtMultimedia import QMediaPlayer
        if status==QMediaPlayer.MediaStatus.EndOfMedia:
            self.clear_caption()
            self.busy=False
            self.current_tag=None
            self.active_changed.emit(False)
            self.report('Lettura terminata.')

    def playback_error(self,*args):
        if not self.closed:
            self.animate_ambient()
            self.clear_caption()
            self.busy=False
            self.active_changed.emit(False)
            self.report('Errore nella riproduzione: '+self.player.errorString())

    def timed_out(self):
        self.animate_ambient()
        self.stop(announce=False)
        self.report('Nessuna risposta. Riprova o cambia servizio.')

    def stop(self,announce=True):
        self.clear_caption()
        self.current_text=''
        self.caption_pages=[]
        self.caption_ends=[]
        self.timeout.stop()
        self.cached_timer.stop()
        self.cached_path=None
        process,self.process=self.process,None
        if process:
            process.kill()
            # finished disposes it; no GUI wait for network or process shutdown.
        if self.player:
            self.player.stop()
        self.busy=False
        self.current_tag=None
        self.active_changed.emit(False)
        if announce:
            self.report('Voce interrotta.')

    def clear_cache(self):
        self.stop(announce=False)
        if self.player:
            self.player.setSource(QUrl())
        count=0
        for path in self.cache.iterdir():
            if path.suffix in ('.mp3','.part'):
                try:
                    path.unlink();count+=1
                except OSError:
                    pass
        self.report(f'Cache svuotata: {count} file.')

    def shutdown(self):
        self.closed=True
        process=self.process
        self.stop(announce=False)
        if process:
            process.waitForFinished(1000)
