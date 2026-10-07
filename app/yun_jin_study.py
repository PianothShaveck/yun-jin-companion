# SPDX-License-Identifier: GPL-3.0-or-later
"""Sparse study prompts and bounded background jobs. No idle decoding or polling keyboard."""
import json
import logging
import random
import sys
import tempfile
import time
from pathlib import Path
from PyQt6.QtCore import QObject,QProcess,QTimer,Qt,pyqtSignal
from PyQt6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QApplication
from yun_jin_ui import STYLE,plain_label,button,icon_button
from yun_jin_dialogs import show_dialog,bring_forward


class StudyPrompt(QDialog):
    def __init__(self,controller):
        pet=controller.pet
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        pet.destroyed.connect(self.deleteLater)
        self.controller=controller;self.pet=pet;self.candidates=[];self.external=False
        self.setStyleSheet(STYLE);self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedWidth(340)
        layout=QVBoxLayout(self);layout.setContentsMargins(18,14,18,16);layout.setSpacing(10)
        header=QHBoxLayout();header.setSpacing(12);header.addWidget(plain_label('Un piccolo ripasso?','section'),1)
        icon_button('close','Ignora',self.hide,header);layout.addLayout(header)
        self.preview=plain_label();self.preview.setStyleSheet('font-size:18px;');layout.addWidget(self.preview)
        row=QHBoxLayout();row.setSpacing(12)
        self.open_button=button('Ripassa',self.open,row,role='primary');row.addStretch()
        button('Non oggi',self.silence_today,row,role='quiet');layout.addLayout(row)
        self.timeout=QTimer(self);self.timeout.setSingleShot(True);self.timeout.setInterval(18000);self.timeout.timeout.connect(self.hide)

    def present(self,candidates,external=False):
        if self.pet.focus_active():return
        self.candidates=candidates;self.external=external
        if external: text=candidates[0]['front']
        else:
            content=json.loads(candidates[0]['content']);text=content['front']
            from yun_jin_srs import CLOZE
            ordinal=candidates[0]['ordinal']
            text=CLOZE.sub(lambda m: '['+(m[3] or '…')+']' if int(m[1])==ordinal else m[2],text)
        self.preview.setText(text[:90] or 'Immagine / audio')
        self.open_button.setText('Ripassa'+(f' · {len(candidates)} carte' if len(candidates)>1 else ' · 1 carta'))
        self.adjustSize();self.move(*self.pet.notification_position(self))
        show_dialog(self,self.pet,quiet=True);self.timeout.start()

    def open(self):
        self.hide()
        if self.external:self.controller.open_anki(cards=self.candidates)
        else:self.controller.open_review(quick_cards=self.candidates)
    def silence_today(self):
        from yun_jin_srs import day_bounds
        self.controller.pet.store.set_preference('study_silenced_until',day_bounds(time.time())[1]);self.hide()
    def hideEvent(self,event):
        self.timeout.stop();super().hideEvent(event)


class StudyTools(QObject):
    anki_changed=pyqtSignal()
    def __init__(self,pet):
        super().__init__(pet);self.pet=pet;self.closed=False;self.active_dialog=None;self.prompt=None
        self.enabled=pet.store.preference('study_prompts',True)
        self.anki_enabled=pet.store.preference('study_anki_enabled',False)
        self.anki_include_suspended=pet.store.preference('study_anki_suspended',False)
        self.anki_seen=[];self.anki_day=None
        self.anki_more=False;self.anki_total=0
        self.anki_path=pet.store.preference('study_anki_path','');self.anki_cards=[];self.anki_valid_until=0;self.anki_requested=False;self.anki_status='Anki non collegato'
        self.anki_detail=''
        self._practice=None
        self.anki_process=None;self.fit_process=None;self.fit_queue=[];self.last_anki=0
        self.next_prompt=pet.store.preference('study_next_prompt',0.)
        if not time.time()<self.next_prompt<time.time()+3*3600:self.schedule_prompt()
        self.timer=QTimer(self);self.timer.setInterval(60000);self.timer.setTimerType(Qt.TimerType.VeryCoarseTimer)
        self.timer.timeout.connect(self.poll)
        if self.enabled or self.anki_enabled:self.timer.start()
        self.fit_delay=QTimer(self);self.fit_delay.setSingleShot(True);self.fit_delay.setInterval(1200);self.fit_delay.timeout.connect(self.start_fit)
        # Leave room for a locked database, its private copy and the bounded
        # reader (6 + 8 seconds), plus interpreter startup. All run off the UI.
        self.anki_timeout=QTimer(self);self.anki_timeout.setSingleShot(True);self.anki_timeout.setInterval(20000)
        self.anki_timeout.timeout.connect(self.anki_timed_out)
        self.fit_timeout=QTimer(self);self.fit_timeout.setSingleShot(True);self.fit_timeout.setInterval(15000)
        self.fit_timeout.timeout.connect(self.cancel_fit)

    def schedule_prompt(self):
        self.next_prompt=time.time()+random.uniform(90*60,150*60)
        self.pet.store.set_preference('study_next_prompt',self.next_prompt)

    def set_enabled(self,enabled):
        self.enabled=bool(enabled);self.pet.store.set_preference('study_prompts',self.enabled)
        if not enabled and self.prompt:self.prompt.hide()
        if enabled or self.anki_enabled:self.timer.start()
        else:self.timer.stop()

    def hide_prompt(self):
        if self.prompt:self.prompt.hide()

    def practice_source(self,external=False):
        from yun_jin_study_rotation import source_key
        return (source_key(self.anki_path) if self.anki_path else 'anki:unlinked') if external else 'native'

    def practice_history(self):
        if self._practice is None:
            from yun_jin_study_rotation import PracticeHistory
            self._practice=PracticeHistory(self.pet.store,self.anki_path)
        return self._practice

    def practice_options(self,external=False,now=None):
        return self.practice_history().options(self.practice_source(external),now)

    def remember_practice(self,cards,external=False,reviewed=False,now=None):
        self.practice_history().record(self.practice_source(external),cards,now,reviewed)

    def can_prompt(self):
        return (not self.closed and not (self.active_dialog and self.active_dialog.isVisible())
                and self.pet.context.can_react(ignore_character=self.pet.character_hidden or self.pet.fullscreen_hidden)
                and not (getattr(self.pet,'bubble',None) and self.pet.bubble.isVisible()))

    def poll(self):
        if self.closed:return
        now=time.time()
        if self.pet.focus_active():self.hide_prompt();return
        if self.anki_enabled and now-self.last_anki>=900:self.refresh_anki()
        if not self.enabled or now<self.next_prompt:return
        self.schedule_prompt()
        if not self.can_prompt() or now<self.pet.store.preference('study_silenced_until',0):return
        from yun_jin_srs import day_bounds
        day=str(int(day_bounds(now)[0]));history=self.pet.store.preference('study_prompt_history',{})
        if history.get('day')!=day:history=dict(day=day,count=0,ids=[])
        if history['count']>=3:return
        # Don't initialize any SRS tables just to discover an empty collection.
        exists=self.pet.store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sr_decks'").fetchone()
        native=self.pet.store.study.hard_candidates(now,3,exclude=[int(i[2:]) for i in history['ids'] if i.startswith('n:')],
            exclude_notes=[int(i[2:]) for i in history.get('notes',[]) if i.startswith('n:')],
            **self.practice_options(now=now)) if exists else []
        blocked=set(self.practice_options(True,now)['cooldown_notes']) if self.anki_enabled else set()
        external=[c for c in self.anki_cards if 'a:'+str(c['id']) not in history['ids']
            and 'a:'+str(c.get('note_id',c['id'])) not in history.get('notes',[])
            and c.get('note_id',c['id']) not in blocked
            and c.get('note_id',c['id']) not in self.anki_seen] if self.anki_enabled and now<self.anki_valid_until else []
        # Both sources are shuffled only AFTER selecting their difficult pool.
        candidates=native or external[:3]
        if not candidates:return
        is_external=not native
        self.remember_practice(candidates,is_external,now=now)
        history['count']+=1;history['ids'] += [('a:' if is_external else 'n:')+str(c['id']) for c in candidates]
        history.setdefault('notes',[]).extend(('a:' if is_external else 'n:')+str(c.get('note_id',c['id'])) for c in candidates)
        self.pet.store.set_preference('study_prompt_history',history)
        if self.prompt is None:self.prompt=StudyPrompt(self)
        self.prompt.present(candidates,is_external)

    def open_review(self,deck_id=None,quick_cards=None):
        self.hide_prompt()
        if self.active_dialog and self.active_dialog.isVisible():bring_forward(self.active_dialog,self.pet);return
        import importlib.util
        if any(importlib.util.find_spec(name) is None for name in ('fsrs','fsrs_rs_python')):
            from yun_jin_dialogs import Messages
            launcher='Mac.command' if sys.platform=='darwin' else 'Windows.cmd' if sys.platform=='win32' else 'Linux.sh'
            Messages.warning(self.pet,'Completa l’aggiornamento','Chiudi Yun Jin e riesegui '+launcher+' dal nuovo pacchetto per installare Studio.')
            return
        from yun_jin_study_ui import ReviewDialog
        self.show_review(ReviewDialog(self.pet,deck_id,quick_cards))

    def show_review(self,dialog):
        self.active_dialog=dialog
        dialog.destroyed.connect(lambda _=None,d=dialog,s=dialog.session:self.review_destroyed(d,s))
        show_dialog(dialog,self.pet)

    def review_destroyed(self,dialog,session):
        if self.active_dialog is not dialog:return
        self.active_dialog=None
        if session and not self.closed:self.optimize(self.pet.store.study.end_session(session))

    def review_closed(self,dialog):
        if self.active_dialog is dialog:self.active_dialog=None
        dialog.deleteLater()
        if self.pet.panel and hasattr(self.pet.panel,'study'):self.pet.panel.study.refresh()

    def set_anki_path(self,path):
        if self.active_dialog and self.active_dialog.external:self.active_dialog.close()
        self.cancel_anki();self.hide_prompt();self.anki_path=path;self.anki_cards=[];self.anki_valid_until=0;self.anki_requested=False;self.anki_detail=''
        self.anki_seen=[];self.anki_day=None
        self.anki_more=False;self.anki_total=0
        self.pet.store.set_preference('study_anki_path',path)
        if path and self.anki_enabled:self.refresh_anki(force=True)
        else:self.anki_status='Anki non collegato';self.anki_changed.emit()

    def set_anki_suspended(self,value):
        self.anki_include_suspended=bool(value);self.pet.store.set_preference('study_anki_suspended',bool(value))
        # Invalidate cached cards immediately, including a pending older worker.
        self.cancel_anki();self.hide_prompt();self.anki_cards=[];self.anki_valid_until=0
        self.anki_more=False;self.anki_total=0
        if self.active_dialog and self.active_dialog.external:self.active_dialog.close()
        if self.anki_enabled:self.refresh_anki(force=True)
        else:self.anki_changed.emit()

    def clear_anki(self):
        if self.active_dialog and self.active_dialog.external:self.active_dialog.close()
        self.cancel_anki();self.anki_cards=[];self.anki_valid_until=0;self.anki_requested=False;self.anki_detail='';self.anki_status='Anki disattivato'
        self.anki_more=False;self.anki_total=0
        self.anki_changed.emit()
        if self.prompt and self.prompt.external:self.prompt.hide()
        if not self.enabled:self.timer.stop()

    def refresh_anki(self,force=False):
        if self.closed or self.anki_process or not self.anki_enabled or not self.anki_path:return
        if not force and self.pet.focus_active():return
        self.timer.start();self.last_anki=time.time();process=QProcess(self);self.anki_process=process
        process.scratch=tempfile.TemporaryDirectory(prefix='yun-jin-anki-job-',ignore_cleanup_errors=True)
        process.setProgram(self.worker_python());process.setArguments(['-X','utf8',str(Path(__file__).with_name('yun_jin_anki.py'))])
        process.finished.connect(lambda code,status:self.anki_finished(process,code))
        process.errorOccurred.connect(lambda _:self.anki_failed(process))
        self.anki_status='Lettura Anki…';self.anki_detail='';self.anki_changed.emit()
        self.anki_timeout.start();process.start()
        if process is self.anki_process:
            process.write(json.dumps({'collection':self.anki_path,'scratch':process.scratch.name,
                'include_suspended':self.anki_include_suspended,'exclude_notes':self.anki_seen,
                'seen_day':self.anki_day,'restart':self.anki_requested,
                **self.practice_options(True)}).encode());process.closeWriteChannel()

    def anki_finished(self,process,code):
        if process is not self.anki_process:return
        self.anki_timeout.stop();self.anki_process=None
        try:
            data=bytes(process.readAllStandardOutput())
            if code or len(data)>3*1024*1024:raise ValueError()
            result=json.loads(data)
            if result.get('error'):
                self.anki_cards=[];self.anki_valid_until=0;self.anki_requested=False
                self.anki_more=False;self.anki_total=0
                self.anki_status=str(result['error'])[:180];self.anki_detail=str(result.get('detail',''))[:300]
                logging.warning('Anki: %s %s',self.anki_status,self.anki_detail)
            else:
                self.anki_cards=result['cards'];self.anki_valid_until=min(result['study_end'],result['checked']+900)
                self.anki_total=count=result.get('total',len(self.anki_cards));self.anki_more=bool(result.get('more',False))
                if self.anki_day!=result['study_start'] or result.get('restarted'):self.anki_seen=[]
                self.anki_day=result['study_start'];self.anki_seen.extend(result.get('skipped',[]))
                self.anki_status=('1 carta selezionata' if count==1 else f'{count} carte selezionate') if count else 'Nessuna carta difficile disponibile oggi'
                if result.get('unsupported'):
                    self.anki_status=('Nessuna carta leggibile: modello non supportato' if not self.anki_cards else self.anki_status+' · alcuni modelli esclusi')
                self.anki_detail='\n'.join(result.get('issues',[]))
        except Exception as exc:
            self.anki_cards=[];self.anki_valid_until=0;self.anki_requested=False
            self.anki_more=False;self.anki_total=0
            self.anki_status='Lettura Anki non riuscita. Riprova.';self.anki_detail=str(exc)[:300]
            logging.warning('Anki worker: %s; %s',exc,bytes(process.readAllStandardError()).decode(errors='replace')[-500:])
        process.scratch.cleanup();process.deleteLater();self.anki_changed.emit()
        if self.anki_requested:
            self.anki_requested=False
            self.open_anki(cards=self.anki_cards)

    def anki_failed(self,process):
        if process is not self.anki_process:return
        self.anki_detail=process.errorString();self.cancel_anki();self.anki_requested=False
        self.anki_cards=[];self.anki_valid_until=0;self.anki_status='Lettura Anki non riuscita. Riprova.'
        self.anki_more=False;self.anki_total=0
        self.anki_changed.emit()

    def anki_timed_out(self):
        self.cancel_anki();self.anki_requested=False;self.anki_cards=[];self.anki_valid_until=0
        self.anki_more=False;self.anki_total=0
        self.anki_status='Anki occupato. Riprova tra poco.';self.anki_changed.emit()

    def cancel_anki(self):
        self.anki_timeout.stop()
        if self.anki_process:
            process=self.anki_process;self.anki_process=None;process.kill();process.waitForFinished(300)
            process.scratch.cleanup();process.deleteLater()

    @staticmethod
    def worker_python():
        # Windows GUI launchers use pythonw.exe, whose standard streams may be absent.
        executable=Path(sys.executable)
        if sys.platform=='win32' and executable.name.lower()=='pythonw.exe':
            console=executable.with_name('python.exe')
            if console.is_file():return str(console)
        return str(executable)

    def open_anki(self,checked=False,cards=None):
        self.hide_prompt()
        if self.active_dialog and self.active_dialog.isVisible():bring_forward(self.active_dialog,self.pet);return
        if not self.anki_enabled:return
        if cards is None and time.time()>=self.anki_valid_until and self.anki_path:
            self.anki_requested=True;self.refresh_anki(force=True);return
        candidates=[]
        if time.time()<self.anki_valid_until:
            if cards is None:
                available=[c for c in self.anki_cards if c.get('note_id',c['id']) not in self.anki_seen]
                if not available and self.anki_path:
                    # Refill from the whole ranked pool, not the previous page.
                    # Only an explicit request may restart an exhausted round.
                    self.anki_requested=True;self.refresh_anki(force=True);return
                # An explicit request may start another round after the pool is exhausted.
                if not available:self.anki_seen=[];available=self.anki_cards
                candidates=available[:3]
            else:candidates=list(cards)[:3]
        if not candidates:
            from yun_jin_dialogs import Messages
            Messages.information(self.pet,'Ripasso Anki',self.anki_status+'\nSolo mazzi studiati oggi, dopo almeno 30 minuti dall’ultimo ripasso della carta.');return
        self.anki_seen.extend(c.get('note_id',c['id']) for c in candidates)
        from yun_jin_study_ui import ReviewDialog
        self.show_review(ReviewDialog(self.pet,external=candidates))

    def optimize(self,deck_ids):
        for deck_id in deck_ids:
            if deck_id not in self.fit_queue:self.fit_queue.append(deck_id)
        if self.fit_queue and not self.fit_process and not self.closed:self.fit_delay.start()

    def start_fit(self):
        if self.closed or self.fit_process or not self.fit_queue:return
        deck_id=self.fit_queue.pop(0);process=QProcess(self);self.fit_process=process
        process.setProgram(self.worker_python());process.setArguments(['-X','utf8',str(Path(__file__).with_name('yun_jin_srs_worker.py'))])
        process.finished.connect(lambda code,status:self.fit_finished(process,deck_id,code))
        process.errorOccurred.connect(lambda _:self.fit_failed(process))
        self.fit_timeout.start();process.start()
        if process is self.fit_process:
            process.write(json.dumps({'database':str(self.pet.store.root/'companion.sqlite3'),'deck_id':deck_id}).encode());process.closeWriteChannel()

    def fit_finished(self,process,deck_id,code):
        if process is not self.fit_process:return
        self.fit_timeout.stop();self.fit_process=None
        try:
            raw=bytes(process.readAllStandardOutput())
            if code or len(raw)>65536:raise ValueError('Optimizer did not complete')
            result=json.loads(raw)
            if result.get('status') in ('waiting','kept','optimized'):
                if result.get('deck_id')!=deck_id:raise ValueError('Optimizer deck mismatch')
                parameters=result.get('parameters')
                if parameters:
                    from fsrs import Scheduler
                    Scheduler(parameters=parameters)
                with self.pet.store.db:
                    self.pet.store.db.execute('''UPDATE sr_decks SET optimizer_status=?,optimized=?,optimized_through=?,
                      parameters=coalesce(?,parameters),generation=generation+? WHERE id=? AND generation=? AND archived=0''',
                      (result['status'],time.time(),result['through'],json.dumps(parameters) if parameters else None,
                       int(parameters is not None),deck_id,result['generation']))
            elif result.get('status')=='failed':logging.warning('FSRS optimizer: %s',result.get('detail',''))
        except Exception:logging.exception('FSRS optimization retained previous parameters')
        process.deleteLater()
        if self.fit_queue:self.fit_delay.start()

    def fit_failed(self,process):
        if process is not self.fit_process:return
        self.cancel_fit()
        if self.fit_queue:self.fit_delay.start()

    def cancel_fit(self):
        self.fit_timeout.stop()
        if self.fit_process:
            process=self.fit_process;self.fit_process=None;process.kill();process.waitForFinished(300);process.deleteLater()

    def shutdown(self):
        self.closed=True;self.timer.stop();self.fit_delay.stop();self.hide_prompt()
        if self.active_dialog:self.active_dialog.close()
        self.cancel_anki();self.cancel_fit();self.fit_queue.clear()
