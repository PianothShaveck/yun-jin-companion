# SPDX-License-Identifier: GPL-3.0-or-later
"""Yun Jin Companion 1.3.0: desktop companion and practice tools."""
import ctypes
import logging
import os
import random
import sys
import time
import uuid
from pathlib import Path
from PyQt6.QtCore import (Qt, QTimer, QUrl, QPoint, QLockFile, QObject, QAbstractNativeEventFilter)
from PyQt6.QtGui import QIcon, QPainter, QColor, QGuiApplication, QImage, QDesktopServices
from PyQt6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                            QMenu, QMessageBox, QSystemTrayIcon)
from yun_jin_core import YunJinPet, BASE, mac_all_spaces
from yun_jin_data import Store, data_directory
from yun_jin_dialogs import Messages, exec_dialog, show_dialog
from yun_jin_panel import Panel, ReminderDialog, STYLE, plain_label, button
from yun_jin_ui import icon_button, icon
from yun_jin_speech import Speech
from yun_jin_platform import action_label, shortcut_help, mac_dock_icon
from yun_jin_music import Metronome, Stopwatch, format_elapsed
from yun_jin_windows import set_process_identity, install_taskbar_icons
from yun_jin_hotkeys import Hotkeys


class Sounds(QObject):
    def __init__(self, pet):
        super().__init__(pet)
        self.pet = pet
        self.enabled = pet.store.preference('sound_enabled', True)
        self.interactions = pet.store.preference('sound_interactions', True)
        self.volume = max(0., min(1., float(pet.store.preference('sound_volume', .28))))
        self.quiet_until = 0.
        self.last_play = 0.
        self.effects = {}
        self.status = ''
        try:
            from PyQt6.QtMultimedia import QSoundEffect, QMediaDevices
            if not QMediaDevices.audioOutputs():
                self.status = 'Nessuna uscita audio.'
            for name in ['hello','saved','reminder','done']:
                path = BASE/'assets'/'sounds'/(name+'.wav')
                if not path.is_file():
                    raise FileNotFoundError(path.name)
                effect = QSoundEffect(self)
                effect.setSource(QUrl.fromLocalFile(str(path)))
                effect.setLoopCount(1)
                effect.setVolume(self.volume)
                self.effects[name] = effect
        except Exception as exc:
            self.status = 'Suoni non disponibili: '+str(exc)
            logging.exception('Audio initialization')

    def play(self, name, preview=False):
        now = time.monotonic()
        if not preview:
            if name!='reminder' and getattr(self.pet,'metronome',None) and self.pet.metronome.running:
                return
            if not self.enabled or time.time()<self.quiet_until:
                return
            if name!='reminder' and not self.interactions:
                return
            if name!='reminder' and now-self.last_play < .4:
                return
        effect=self.effects.get(name)
        if effect is None:
            return
        for other in self.effects.values():
            other.stop()
        effect.setVolume(self.volume)
        effect.play()
        self.last_play=now


class ReminderCard(QDialog):
    def __init__(self, pet):
        super().__init__(pet, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.pet=pet
        self.rid=None
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet(STYLE)
        self.setWindowIcon(pet.windowIcon())
        self.setFixedWidth(380)
        layout=QVBoxLayout(self); layout.setContentsMargins(18,14,18,16); layout.setSpacing(12)
        head=QHBoxLayout(); head.setSpacing(12)
        self.heading=plain_label('Promemoria'); self.heading.setObjectName('section'); head.addWidget(self.heading,1)
        icon_button('note','Elenco promemoria',lambda:pet.open_panel(tab=1),head)
        icon_button('close','Nascondi',self.hide,head); layout.addLayout(head)
        self.title=plain_label(); self.title.setStyleSheet('font-size: 17px;'); layout.addWidget(self.title)
        row=QHBoxLayout(); row.setSpacing(12)
        button('Fatto',self.complete,row,glyph='check',role='primary')
        button('Tra 10 min',self.snooze,row,glyph='clock'); row.addStretch(); layout.addLayout(row)

    def present(self, rows):
        if not rows:
            self.hide()
            return
        self.rid=rows[0]['id']
        self.heading.setText('Promemoria'+(f' · {len(rows)}' if len(rows)>1 else ''))
        self.title.setText(rows[0]['title'][:400])
        self.adjustSize()
        rect=self.pet.current_screen().availableGeometry()
        x=max(rect.left(),min(self.pet.x()-self.width()+30,rect.right()+1-self.width()))
        y=max(rect.top(),min(self.pet.y()-self.height()-8,rect.bottom()+1-self.height()))
        self.move(x,y)
        self.show()

    def complete(self):
        if self.rid:
            self.pet.complete_reminder(self.rid)

    def snooze(self):
        if self.rid:
            self.pet.snooze_reminder(self.rid,10)


class Companion(YunJinPet):
    def __init__(self, store):
        self.store=store
        self.panel=None
        self.card=None
        self.sound=None
        self.speech=None
        self.voice_restore=None
        self.music_restore=None
        self.metronome=None
        self.pending_feedback=None
        self.focus_reminder=self.store.preference('focus_reminder','')
        self.hotkey_status=''
        self.announced=set()
        self.due_count=0
        self.closing=False
        self.reminder_dialog=None
        self.mac_overlay=None
        self.updates=None
        self.context=None
        super().__init__()
        icon=QIcon(str(BASE/'favicon.png'))
        if not icon.isNull():
            self.setWindowIcon(icon)
            QApplication.instance().setWindowIcon(icon)
        self.setAcceptDrops(True)
        self.use_extra_animations=self.store.preference('extra_animations',True)
        self.sound=Sounds(self)
        from yun_jin_bubble import SpeechBubble
        self.bubble=SpeechBubble(self)
        self.speech_caption=''
        self.shortcut_timer=QTimer(self);self.shortcut_timer.setSingleShot(True)
        self.shortcut_timer.setInterval(3000);self.shortcut_timer.timeout.connect(self.clear_shortcut_feedback)
        self.speech=Speech(self)
        self.speech.caption_changed.connect(self.show_caption)
        self.speech.active_changed.connect(self.voice_animation)
        self.speech.status_changed.connect(self.speech_status_animation)
        self.metronome=Metronome(self)
        self.stopwatch=Stopwatch(store,self)
        self.metronome.active_changed.connect(self.music_animation)
        self.checkpoint_timer=QTimer(self)
        self.checkpoint_timer.timeout.connect(lambda:self.stopwatch.save() if self.stopwatch.running else None)
        self.checkpoint_timer.start(5000)
        self.hotkeys=Hotkeys(self)
        self.card=ReminderCard(self)
        self.tray=QSystemTrayIcon(self.windowIcon(),self)
        self.tray.setToolTip('Yun Jin')
        tray_menu=QMenu(self)
        self.populate_context_menu(tray_menu)
        tray_menu.aboutToShow.connect(lambda: self.populate_context_menu(tray_menu))
        self.tray.setContextMenu(tray_menu)
        self.tray_menu=tray_menu
        self.tray.activated.connect(self.tray_activated)
        self.tray.messageClicked.connect(lambda: self.open_panel(tab=1))
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.reminder_timer=QTimer(self)
        self.reminder_timer.timeout.connect(self.poll_reminders)
        self.reminder_timer.start(1000)
        QTimer.singleShot(1500,self.poll_reminders)
        from yun_jin_updates_ui import Updates
        self.updates=Updates(self)
        from yun_jin_context import Context
        self.context=Context(self)
        from yun_jin_study import StudyTools
        self.study_tools=StudyTools(self)

    def tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,QSystemTrayIcon.ActivationReason.DoubleClick):
            self.open_panel()

    def reveal(self):
        self.show()
        self.ensure_visible()
        self.raise_()

    def focus_row(self):
        if not self.focus_reminder:
            return None
        return next((r for r in self.store.reminders() if r['id']==self.focus_reminder),None)

    def focus_active(self):
        row=self.focus_row()
        return bool(row and row['status']=='pending' and row['due']>time.time())

    def start_focus(self,minutes=25):
        if getattr(self,"study_tools",None): self.study_tools.hide_prompt()
        minutes=max(1,min(180,int(minutes)))
        self.store.set_preference('focus_minutes',minutes)
        previous=self.focus_row()
        if previous and previous['status']=='pending':
            self.store.delete_reminder(previous['id'])
        self.focus_reminder=self.store.add_reminder(
            f'Sessione di {minutes} minuti terminata: è il momento di una pausa!',
            time.time()+minutes*60)
        self.store.set_preference('focus_reminder',self.focus_reminder)
        if not self.locked and self.state not in ('voice','voice_wait','conducting'):
            self.cancel();self.idle()
        self.refresh_reminders()
        if self.panel:
            self.panel.refresh_focus()

    def stop_focus(self):
        row=self.focus_row()
        if row and row['status']=='pending':
            self.store.delete_reminder(row['id'])
        self.focus_reminder=''
        self.store.set_preference('focus_reminder','')
        self.refresh_reminders()
        if self.panel:
            self.panel.refresh_focus()

    def toggle_focus(self):
        if self.focus_active():self.stop_focus()
        else:self.start_focus(self.panel.focus_minutes.value() if self.panel else self.store.preference('focus_minutes',25))

    def start_stopwatch(self):
        if not self.stopwatch.running:
            self.stopwatch.start();self.queue_feedback('chronometer','review')

    def toggle_stopwatch(self):
        if self.stopwatch.running:self.stopwatch.pause()
        else:self.start_stopwatch()

    def lap_stopwatch(self):
        if self.stopwatch.lap() is not None:self.queue_feedback('chronometer','wave')

    def start_metronome(self,config=None):
        if config is None:
            config=self.panel.music.current_config() if self.panel else self.metronome.settings()
        self.speech.stop(announce=False)
        try:
            if self.metronome.start(config):return True
        except (ImportError,OSError,RuntimeError,ValueError):
            logging.exception('Metronome start')
            self.metronome.stop(announce=False)
            self.metronome.status='Audio non disponibile. Controlla l’uscita audio.'
            self.metronome.changed.emit()
        self.open_panel(tab=5,subtab=0)
        return False

    def toggle_metronome(self):
        if self.metronome.running:self.metronome.stop()
        else:self.start_metronome()

    def decide(self,now):
        if self.focus_active() or (self.metronome and self.metronome.running):
            self.next_decision=now+5
            return
        if self.mode=='asleep':
            super().decide(now)
            return
        from yun_jin_core import ANIMATIONS
        dances=[name for name in ('dance16','pirouette16')
                if name in ANIMATIONS and name!=self.previous_action]
        if (self.use_extra_animations and dances and self.mode!='quiet'
                and now-self.last_cursor_motion<90
                and random.random()<(0.16 if self.mode=='lively' else 0.07)):
            self.previous_action=random.choice(dances)
            self.sequence([(self.previous_action,1)])
            return
        super().decide(now)

    def performance(self):
        from yun_jin_core import ANIMATIONS
        dances=[(name,1) for name in ('dance16','pirouette16') if name in ANIMATIONS]
        if self.use_extra_animations and dances:
            self.sequence([('wave',1),*dances,('wave',1)])
        else:
            super().performance()

    def event_animation(self,event,fallback):
        if self.use_extra_animations:
            return self.sheet.event_animations.get(event,fallback)
        return fallback

    def set_extra_animations(self,value):
        self.use_extra_animations=value
        self.store.set_preference('extra_animations',value)
        if self.state=='voice':
            self.play(self.event_animation('speaking','review'))
        elif self.state=='voice_wait':
            self.play(self.event_animation('preparing','wait'))
        elif self.state=='conducting':
            self.play(self.event_animation('conducting','work'))

    def open_guide(self):
        self.open_external(QUrl.fromLocalFile(str(BASE.parent/'Guida.pdf')))

    def open_external(self,url,owner=None):
        """Save the editor, then yield the foreground to the requested app."""
        try:
            if self.panel:self.panel.save_note()
        except Exception as exc:
            Messages.warning(owner or self,'Appunto non salvato',str(exc))
            return False
        if not QDesktopServices.openUrl(url):
            Messages.warning(owner or self,'Impossibile aprire','Non riesco ad aprire questo elemento.')
            return False
        if owner is not None and owner is not self and owner is not self.panel:
            owner.hide()
        if self.panel and self.panel.isVisible():
            self.panel.hide();self.panel_closed()
        return True

    def show_caption(self,text):
        self.speech_caption=text
        if not self.shortcut_timer.isActive():self.bubble.present(text)

    def clear_shortcut_feedback(self):
        self.shortcut_timer.stop()
        self.bubble.present(self.speech_caption)

    def shortcut_feedback(self,action):
        if self.closing or (self.panel and self.panel.isVisible() and not self.panel.isMinimized()):return
        if action=='stopwatch_toggle':
            if self.stopwatch.running:
                text='Cronometro ripreso' if self.stopwatch.accumulated else 'Cronometro avviato'
            else:text='Cronometro in pausa · '+format_elapsed(self.stopwatch.elapsed())
        elif action=='stopwatch_lap':
            text=(f'Parziale {len(self.stopwatch.laps)} · '+format_elapsed(self.stopwatch.laps[-1]['split'])
                  if self.stopwatch.running and self.stopwatch.laps else 'Avvia il cronometro per registrare un parziale.')
        elif action=='stopwatch_reset':text='Cronometro azzerato'
        elif action=='metronome_toggle':text='Metronomo avviato' if self.metronome.running else 'Metronomo fermato'
        elif action=='focus_toggle':
            text=f'Focus · {self.store.preference("focus_minutes",25)} min' if self.focus_active() else 'Focus interrotto'
        elif action=='pet_pause':text='Yun Jin in pausa' if self.paused else 'Yun Jin riprende'
        elif action=='quiet':text='Silenzio per un’ora' if time.time()<self.sound.quiet_until else 'Silenzio disattivato'
        elif action=='stop':text='Voce interrotta'
        else:return
        self.shortcut_timer.start()
        self.bubble.present(text)

    def music_animation(self,active):
        if active and self.speech.category == 'ambient':
            self.speech.stop(announce=False)
        if active and self.is_sleeping():
            self.wake_up(lambda:self.music_animation(True) if self.metronome.running else None)
            return
        if active:
            if self.music_restore is None:
                self.music_restore=(self.paused,self.locked,self.animation)
            self.cancel();self.paused=False;self.state='conducting'
            self.play(self.event_animation('conducting','work'))
        elif self.music_restore is not None:
            paused,locked,animation=self.music_restore;self.music_restore=None
            if self.state=='conducting':
                if locked:self.hold_pose(animation)
                else:self.idle()
                self.paused=paused

    def animate(self,dt):
        if self.state=='conducting' and self.metronome and self.metronome.running:
            from yun_jin_core import ANIMATIONS
            self.frame=min(ANIMATIONS[self.animation][1]-1,int(self.metronome.phase()*ANIMATIONS[self.animation][1]))
            self.update_frame()
        else:
            super().animate(dt)

    def tick(self):
        if self.metronome and self.metronome.running and self.state=='idle' and not self.locked:
            self.state='conducting'
            self.play(self.event_animation('conducting','work'))
        super().tick()

    def preview_animation(self,name):
        from yun_jin_core import ANIMATIONS
        if name not in ANIMATIONS:
            self.open_panel(tab=3)
            self.panel.voice_status.setText('Animazione non trovata: controlla la cartella assets.')
            return
        self.speech.stop(announce=False)
        self.metronome.stop()
        if self.panel:
            self.panel.save_note()
            self.panel.hide()
            self.panel_closed()
        self.sequence([(name,3)])

    def read_clipboard(self):
        text=QApplication.clipboard().text()
        self.open_panel(tab=3)
        self.speech.speak(text)

    def stop_speech(self):
        self.speech.stop()

    def speech_status_animation(self, *_):
        if self.speech.category == 'ambient':
            return
        if self.speech.busy and self.speech.process is not None:
            self.voice_animation(True,preparing=True)
        elif not self.speech.busy and self.state=='voice_wait':
            self.voice_animation(False)

    def voice_animation(self,active,preparing=False):
        if self.speech.category == 'ambient':
            return
        if active and self.is_sleeping():
            self.wake_up(lambda:self.voice_animation(True,preparing=self.speech.process is not None)
                         if self.speech.busy else None)
            return
        if active:
            if self.metronome.running:
                self.metronome.stop()
            if self.voice_restore is None:
                self.voice_restore=(self.paused,self.locked,self.animation)
            elif self.state==('voice_wait' if preparing else 'voice'):
                return
            self.cancel()
            self.paused=False
            self.state='voice_wait' if preparing else 'voice'
            self.play(self.event_animation('preparing','wait') if preparing else self.event_animation('speaking','review'))
        elif self.voice_restore is not None:
            paused,locked,animation=self.voice_restore
            self.voice_restore=None
            if self.state in ('voice','voice_wait'):
                if locked:
                    self.hold_pose(animation)
                else:
                    self.idle()
                self.paused=paused

    def greet(self):
        super().greet()
        if self.sound:
            self.sound.play('hello')

    def open_panel(self, checked=False, tab=0, subtab=None):
        self.clear_shortcut_feedback()
        if self.panel is None:
            self.panel=Panel(self)
        # Opening a tool must not change the user's explicit pause setting.
        self.panel.show_page(tab,subtab)
        self.panel.refresh_reminders()
        show_dialog(self.panel, self)

    def new_note(self):
        self.open_panel();self.panel.new_note()

    def focus_tool(self, widget):
        if self.mac_overlay and self.mac_overlay.enabled:
            try:
                self.mac_overlay.native.focus(widget)
            except Exception as exc:
                self.mac_overlay.fail(exc)
                widget.activateWindow()
        else:
            widget.activateWindow()

    def set_mac_overlay(self, enabled):
        from yun_jin_macos import PREFERENCE
        if self.mac_overlay is None:
            return False
        success=self.mac_overlay.set_enabled(enabled)
        if success:
            self.store.set_preference(PREFERENCE,bool(enabled))
        if not self.mac_overlay.enabled:
            mac_dock_icon(BASE/'favicon.icns')
        if self.panel:
            self.panel.sync_mac_overlay()
        return success

    def panel_closed(self):
        self.last_tick=time.monotonic()
        self.flush_feedback()

    def new_reminder(self, checked=False, existing=None):
        if self.reminder_dialog is not None:
            self.reminder_dialog.raise_()
            self.focus_tool(self.reminder_dialog)
            return
        self.reminder_dialog=ReminderDialog(self,existing)
        try:
            exec_dialog(self.reminder_dialog, self)
        finally:
            self.reminder_dialog.deleteLater()
            self.reminder_dialog=None

    def saved_feedback(self):
        self.sound.play('saved')
        self.queue_feedback('saved','review')

    def queue_feedback(self,event,fallback):
        # Defer feedback while editing, without interrupting explicit pauses.
        if self.locked or self.paused:
            return
        self.pending_feedback=(event,fallback)
        self.flush_feedback()

    def flush_feedback(self):
        if (self.pending_feedback is None or self.paused or self.locked
                or self.menu_open or self.drag_anchor is not None
                or self.following or self.state=='follow_pending'
                or self.is_sleeping() or self.mode=='asleep'
                or self.speech.busy or self.metronome.running or (self.panel and self.panel.isVisible())):
            return
        event,fallback=self.pending_feedback
        self.pending_feedback=None
        self.sequence([(self.event_animation(event,fallback),1)])

    def poll_reminders(self):
        if self.closing:
            return
        try:
            rows=self.store.mark_due()
            badge_changed = self.due_count != len(rows)
            self.due_count=len(rows)
            new=[r for r in rows if r['id'] not in self.announced]
            focus_due=any(r['id']==self.focus_reminder for r in new)
            if new:
                self.announced.update(r['id'] for r in new)
                self.card.present(rows)
                self.sound.play('reminder')
                message=new[0]['title']
                if len(new)>1:
                    message+=f'. Hai anche altri {len(new)-1} promemoria.'
                self.speech.speak(message,category='reminder',tag=new[0]['id'])
                if focus_due:
                    self.queue_feedback('break','wave')
                elif not self.paused and not self.menu_open and self.drag_anchor is None and not self.locked and not self.following and not self.is_sleeping() and self.state not in ('voice','voice_wait','conducting','follow_pending'):
                    self.sequence([(self.event_animation('reminder','wave'),2),('wait',1)])
                if self.tray.isVisible():
                    message=new[0]['title'][:200]+(f' (+{len(new)-1} altri)' if len(new)>1 else '')
                    self.tray.showMessage('Yun Jin · Promemoria',message,QSystemTrayIcon.MessageIcon.Information,10000)
            if self.panel and self.panel.isVisible():
                self.panel.refresh_reminders()
                self.panel.refresh_focus()
            self.flush_feedback()
            if badge_changed:
                self.update()
            if self.context:
                self.context.dispatch()
        except Exception:
            logging.exception('Reminder poll failed')
            self.reminder_timer.stop()
            Messages.critical(self,'Promemoria non disponibili','Non riesco a leggere o salvare i promemoria. Riavvia il pet dopo aver controllato il log nella cartella dati.')

    def refresh_reminders(self):
        rows=self.store.mark_due()
        self.due_count=len(rows)
        active_due={r['id'] for r in rows}
        if self.speech.current_tag and self.speech.current_tag not in active_due:
            self.speech.stop(announce=False)
        self.announced.intersection_update(active_due)
        if self.panel:
            self.panel.refresh_reminders(force=True)
        if self.card and self.card.isVisible():
            self.card.present(rows)
        self.update()

    def complete_reminder(self,rid):
        if self.speech.current_tag==rid:
            self.speech.stop(announce=False)
        self.store.complete(rid)
        self.sound.play('done')
        self.refresh_reminders()
        self.queue_feedback('completed','wave')

    def snooze_reminder(self,rid,minutes=10):
        if self.speech.current_tag==rid:
            self.speech.stop(announce=False)
        self.store.snooze(rid,minutes)
        self.announced.discard(rid)
        self.sound.play('saved')
        self.refresh_reminders()

    def paintEvent(self,event):
        super().paintEvent(event)
        if self.due_count:
            painter=QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QColor('#9f496a'))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(self.width()-25,4,22,22)
            painter.setPen(QColor('white'))
            painter.drawText(self.width()-25,4,22,22,Qt.AlignmentFlag.AlignCenter,str(min(99,self.due_count)))

    @staticmethod
    def accepts_mime(mime):
        return mime.hasUrls() or mime.hasImage() or mime.hasText()

    def dragEnterEvent(self,event):
        if self.accepts_mime(event.mimeData()):
            event.acceptProposedAction()

    def dragMoveEvent(self,event):
        if self.accepts_mime(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self,event):
        self.capture_mime(event.mimeData())
        event.acceptProposedAction()

    def capture_clipboard(self):
        mime=QApplication.clipboard().mimeData()
        if mime is None or not self.accepts_mime(mime):
            self.open_panel()
            self.panel.status.setText('Nessun contenuto negli appunti.')
            return
        self.capture_mime(mime)

    def capture_mime(self,mime):
        # Snapshot clipboard contents before opening windows or changing focus.
        if mime.hasUrls():
            local=[u.toLocalFile() for u in mime.urls() if u.isLocalFile()]
            remote=[u.toString() for u in mime.urls() if not u.isLocalFile()]
            if local:
                self.add_paths(local)
            if remote:
                self.add_text('\n'.join(remote))
            return
        if mime.hasImage():
            image=QImage(mime.imageData())
            if not image.isNull():
                name=uuid.uuid4().hex+'.png'
                path=self.store.root/'attachments'/name
                if not image.save(str(path),'PNG'):
                    raise IOError('Impossibile salvare l’immagine.')
                self.open_panel()
                self.panel.save_note()
                rid=self.store.save_note('Immagine · '+time.strftime('%d/%m %H:%M'),'','attachment:'+name)
                self.panel.load_note(rid)
                self.saved_feedback()
                return
        if mime.hasText():
            self.add_text(mime.text())

    def add_text(self,text):
        if not text.strip():
            return
        self.open_panel()
        self.panel.save_note()
        rid=self.store.save_note('',text)
        self.panel.load_note(rid)
        self.saved_feedback()

    def add_paths(self,paths):
        self.open_panel()
        self.panel.save_note()
        rid=None
        for raw in paths:
            path=Path(raw).expanduser().resolve()
            if path.exists():
                rid=self.store.save_note(path.name,'',str(path))
        if rid:
            self.panel.load_note(rid)
            self.saved_feedback()

    def quiet_hour(self):
        self.speech.stop(announce=False)
        self.sound.quiet_until=time.time()+3600
        if self.panel:
            self.panel.status.setText('Suoni sospesi per un’ora.')

    def toggle_quiet(self):
        if time.time()<self.sound.quiet_until:
            self.sound.quiet_until=0.
            if self.panel:self.panel.status.clear()
        else:self.quiet_hour()

    def add_companion_menu(self,menu):
        menu.addAction(self.hotkeys.label('Pannello…','panel'),self.open_panel)
        tools=menu.addMenu('Strumenti')
        tools.addAction('Appunti…',self.open_panel)
        tools.addAction(self.hotkeys.label('Importa appunti copiati','capture'),self.capture_clipboard)
        tools.addSeparator()
        tools.addAction(self.hotkeys.label('Nuovo promemoria…','reminder'),self.new_reminder)
        tools.addAction('Promemoria…',lambda:self.open_panel(tab=1))
        tools.addSeparator()
        tools.addAction(self.hotkeys.label('Studio…','study'),lambda:self.open_panel(tab=6))
        tools.addAction(self.hotkeys.label('Focus…','focus_open'),lambda:self.open_panel(tab=4))
        tools.addAction(self.hotkeys.label('Metronomo…','metronome_open'),lambda:self.open_panel(tab=5,subtab=0))
        tools.addAction(self.hotkeys.label('Cronometro…','stopwatch_open'),lambda:self.open_panel(tab=5,subtab=1))
        voice=menu.addMenu('Voce')
        voice.addAction(self.hotkeys.label('Leggi testo copiato','read'),self.read_clipboard)
        voice.addAction(self.hotkeys.label('Interrompi','stop'),self.stop_speech)
        voice.addSeparator()
        voice.addAction('Impostazioni voce…',lambda:self.open_panel(tab=3))
        if self.sound and time.time()<self.sound.quiet_until:
            voice.addAction('Riattiva suoni',lambda:setattr(self.sound,'quiet_until',0.))
        else:
            voice.addAction('Silenzio per 1 ora',self.quiet_hour)

    def add_companion_footer(self,menu):
        menu.addSeparator()
        menu.addAction('Impostazioni…',lambda:self.open_panel(tab=2))
        menu.addAction('Guida',self.open_guide)

    def closeEvent(self,event):
        if self.panel:
            try:
                self.panel.save_note()
            except Exception as exc:
                Messages.warning(self,'Appunto non salvato',str(exc))
                event.ignore()
                return
        self.closing=True
        self.shortcut_timer.stop()
        if getattr(self,"study_tools",None):self.study_tools.shutdown()
        if self.context:
            self.context.shutdown()
        if self.updates:
            self.updates.shutdown()
        self.save_settings()
        self.timer.stop()
        self.reminder_timer.stop()
        self.checkpoint_timer.stop()
        self.metronome.stop(announce=False)
        self.stopwatch.pause()
        self.hotkeys.close()
        self.speech.shutdown()
        self.tray.hide()
        if self.panel:
            self.panel.hide()
        if self.card:
            self.card.hide()
        event.accept()
        QApplication.instance().quit()


def main():
    set_process_identity()
    root=data_directory()
    logging.basicConfig(filename=str(root/'yun-jin.log'),level=logging.WARNING,
                        format='%(asctime)s %(levelname)s %(message)s')
    if sys.platform=='darwin':
        # Qt-owned file dialogs can follow the same fullscreen/layer rules.
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
    app=QApplication(sys.argv)
    app.setApplicationName('Yun Jin')
    app.setQuitOnLastWindowClosed(False)
    icon_path=BASE/('favicon.ico' if sys.platform=='win32' else 'favicon.png')
    app.setWindowIcon(QIcon(str(icon_path)))
    install_taskbar_icons(app, BASE/'favicon.ico')
    lock=QLockFile(str(root/'companion.lock'))
    lock.setStaleLockTime(0)
    if not lock.tryLock(50):
        Messages.information(None,'Yun Jin è già aperta',shortcut_help())
        return 0
    store=None; pet=None
    def exception_hook(kind,value,tb):
        logging.error('Unhandled exception',exc_info=(kind,value,tb))
        Messages.critical(pet,'Yun Jin · errore',str(value)+'\n\nI dettagli sono in '+str(root/'yun-jin.log'))
    sys.excepthook=exception_hook
    try:
        store=Store(root)
        pet=Companion(store)
        if sys.platform=='darwin' and app.platformName()=='cocoa':
            from yun_jin_macos import MacOverlay, PREFERENCE
            try:
                pet.mac_overlay=MacOverlay(app,pet)
            except Exception:
                logging.exception('Unable to initialize macOS overlay')
        if sys.platform=='win32':
            app._yun_jin_taskbar_icons.apply(pet)
        pet.show()
        pet.context.start()
        mac_all_spaces(pet)
        if pet.mac_overlay:
            pet.mac_overlay.set_enabled(store.preference(PREFERENCE,True))
        mac_dock_icon(BASE/'favicon.icns')
        QTimer.singleShot(0,lambda:mac_dock_icon(BASE/'favicon.icns'))
        # The update helper only commits the successful restart after the GUI
        # has reached its event loop with the new code and loaded all sprites.
        ready=os.environ.pop('YUN_JIN_UPDATE_READY','')
        token=os.environ.pop('YUN_JIN_UPDATE_TOKEN','')
        if ready and token:
            QTimer.singleShot(0,lambda:Path(ready).write_text(token,encoding='utf-8'))
        app.aboutToQuit.connect(pet.save_settings)
        app.aboutToQuit.connect(lambda: pet.panel.save_note() if pet.panel else None)
        return app.exec()
    except Exception as exc:
        logging.exception('Startup failed')
        Messages.critical(pet,'Yun Jin · avvio non riuscito',str(exc)+'\n\nCartella dati: '+str(root))
        return 1
    finally:
        if store:
            store.close()
        lock.unlock()
