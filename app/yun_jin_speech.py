# SPDX-License-Identifier: GPL-3.0-or-later
"""Qt speech controller: no GUI blocking, no automatic provider switching."""
import json
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


class Speech(QObject):
    status_changed=pyqtSignal(str)
    active_changed=pyqtSignal(bool)

    def __init__(self,pet):
        super().__init__(pet)
        self.pet=pet
        self.process=None
        self.player=None
        self.output=None
        self.busy=False
        self.closed=False
        self.current_tag=None
        self.category='manual'
        self.status=''
        self.cache=pet.store.root/'voice-cache'
        self.cache.mkdir(exist_ok=True)
        self.timeout=QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self.timed_out)
        try:
            from PyQt6.QtMultimedia import QMediaPlayer,QAudioOutput
            self.player=QMediaPlayer(self)
            self.output=QAudioOutput(self)
            self.player.setAudioOutput(self.output)
            self.player.playbackStateChanged.connect(self.playback_state)
            self.player.mediaStatusChanged.connect(self.media_status)
            self.player.errorOccurred.connect(self.playback_error)
        except Exception as exc:
            self.status='Riproduzione vocale non disponibile: '+str(exc)

    def pref(self,key,default):
        return self.pet.store.preference('tts_'+key,default)

    def set_pref(self,key,value):
        self.pet.store.set_preference('tts_'+key,value)
        if key=='enabled' and not value:
            self.stop()
        if key=='volume' and self.output:
            self.output.setVolume(value/100)

    def report(self,text):
        self.status=text
        self.status_changed.emit(text)

    def speak(self,text,category='manual',tag=None,preview=False):
        text=str(text).strip()
        if not text:
            self.report('Nessun testo da leggere.')
            return False
        if len(text)>3000:
            self.report('Massimo 3000 caratteri. Seleziona un passaggio.')
            return False
        if not preview and not self.pref('enabled',True):
            self.report('Attiva la voce.')
            return False
        if not preview and time.time()<self.pet.sound.quiet_until:
            self.report('Silenzio attivo. Riattiva i suoni dal menu.')
            return False
        if category=='reminder' and (self.busy or (getattr(self.pet,'metronome',None) and self.pet.metronome.running) or not self.pref('reminders',True)):
            return False
        if self.player is None:
            self.report('Qt Multimedia non è disponibile: reinstalla le dipendenze.')
            return False
        self.stop(announce=False)
        self.category=category
        self.current_tag=tag
        self.busy=True
        language=self.pref('language','it')
        provider=self.pref('provider','edge')
        default_voice=VOICES.get(language,VOICES['it'])[0][1]
        voice=self.pref('voice_'+language,default_voice)
        job={'text':text,'provider':provider,'voice':voice,'language':language,
             'rate':(int(self.pref('rate',20)) if provider=='edge' else (-1 if self.pref('google_slow',0) else 0)),
             'pitch':(int(self.pref('pitch',15)) if provider=='edge' else 0),
             'cache':str(self.cache)}
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
        self.timeout.start(45000)
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
            path=Path(reply['path']).resolve()
            path.relative_to(self.cache.resolve())
            if not path.is_file() or path.suffix!='.mp3':
                raise ValueError('File vocale non valido.')
            if self.category=='reminder' and self.current_tag:
                active={r['id'] for r in self.pet.store.reminders()}
                if self.current_tag not in active:
                    self.busy=False
                    return
            self.output.setVolume(max(0,min(100,int(self.pref('volume',70))))/100)
            self.player.setSource(QUrl.fromLocalFile(str(path)))
            self.player.play()
            self.report('Lettura…')
        except Exception as exc:
            self.busy=False
            self.current_tag=None
            self.report('Voce non disponibile: '+str(exc)+' Riprova o cambia servizio.')

    def playback_state(self,state):
        from PyQt6.QtMultimedia import QMediaPlayer
        self.active_changed.emit(state==QMediaPlayer.PlaybackState.PlayingState)

    def media_status(self,status):
        from PyQt6.QtMultimedia import QMediaPlayer
        if status==QMediaPlayer.MediaStatus.EndOfMedia:
            self.busy=False
            self.current_tag=None
            self.active_changed.emit(False)
            self.report('Lettura terminata.')

    def playback_error(self,*args):
        if not self.closed:
            self.busy=False
            self.active_changed.emit(False)
            self.report('Errore nella riproduzione: '+self.player.errorString())

    def timed_out(self):
        self.stop(announce=False)
        self.report('Nessuna risposta. Riprova o cambia servizio.')

    def stop(self,announce=True):
        self.timeout.stop()
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
