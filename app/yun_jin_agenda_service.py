# SPDX-License-Identifier: GPL-3.0-or-later
"""Agenda notifications driven by the companion's existing one-second tick."""
import logging
import sqlite3
import time
from datetime import datetime

from PyQt6.QtCore import QObject, Qt, QUrl
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout
from yun_jin_ui import STYLE, plain_label, button, icon_button
from yun_jin_dialogs import show_dialog


class AgendaCard(QDialog):
    def __init__(self, service):
        pet = service.pet
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.service = service
        self.alert = None
        pet.destroyed.connect(self.deleteLater)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle('Yun Jin · Agenda')
        self.setWindowIcon(pet.windowIcon()); self.setStyleSheet(STYLE)
        self.setFixedWidth(380)
        layout = QVBoxLayout(self); layout.setContentsMargins(20,16,20,18); layout.setSpacing(12)
        top = QHBoxLayout(); top.setSpacing(12)
        self.heading = plain_label('', 'section'); top.addWidget(self.heading,1)
        icon_button('calendar','Apri agenda',self.open_agenda,top)
        icon_button('close','Chiudi avviso',self.dismiss,top); layout.addLayout(top)
        self.title = plain_label(); self.title.setStyleSheet('font-size:19px;font-weight:600;')
        layout.addWidget(self.title)
        self.when = plain_label('', 'muted'); layout.addWidget(self.when)
        self.details = plain_label(); layout.addWidget(self.details)
        actions = QHBoxLayout(); actions.setSpacing(12)
        self.stop_button = button('Ferma',self.dismiss,actions,glyph='stop',role='primary')
        self.snooze_button = button('Tra 10 min',self.snooze,actions,glyph='clock')
        actions.addStretch(); layout.addLayout(actions)

    def present(self, alerts):
        if not alerts:
            self.alert = None; self.hide(); return
        self.alert = alerts[0]
        alarm = self.alert['kind'] == 'alarm'
        self.heading.setText(('Sveglia' if alarm else 'Calendario') +
                             (f' · {len(alerts)}' if len(alerts)>1 else ''))
        self.title.setText(self.alert['title'][:400])
        scheduled = datetime.fromtimestamp(self.alert['scheduled_at'])
        self.when.setText(scheduled.strftime('%d/%m')+' · Tutto il giorno' if self.alert.get('all_day')
                          else scheduled.strftime('%d/%m · %H:%M'))
        self.details.setText(self.alert.get('details','')[:300])
        self.details.setVisible(bool(self.details.text()))
        self.stop_button.setText('Ferma' if alarm else 'Chiudi')
        self.snooze_button.setText(f'Tra {self.alert.get("snooze_minutes",10)} min')
        self.adjustSize()
        self.move(*self.service.pet.notification_position(self))
        show_dialog(self,self.service.pet,quiet=True)

    def dismiss(self):
        if self.alert:self.service.dismiss(self.alert['id'])

    def snooze(self):
        if self.alert:self.service.snooze(self.alert['id'])

    def open_agenda(self):
        self.service.pet.open_panel(tab=9 if self.alert and self.alert['kind']=='alarm' else 8)

    def closeEvent(self,event):
        # dismiss() may immediately present the next alert. Let it decide when
        # to hide, rather than closing that next card at the end of this event.
        event.ignore(); self.dismiss()

    def reject(self):
        self.dismiss()


class AgendaService(QObject):
    def __init__(self,pet):
        super().__init__(pet)
        self.pet = pet
        self.model = pet.store.agenda
        self.card = None
        self.effect = None
        self.ringing = set()
        self.ring_until = 0.
        self.closed = False
        self.retry_at = 0.
        self.day = datetime.now().date()
        self.day_check = 0.
        self.revision = self.model.revision

    def tick(self):
        if self.closed or getattr(self.pet,'closing',False):return
        now = time.monotonic()
        if self.ringing and (now >= self.ring_until or not self.sound_allowed()):self.stop_ring()
        if now < self.retry_at:return
        try:
            alerts = self.model.poll()
            changed = self.model.revision != self.revision
            if alerts or changed:
                self.revision = self.model.revision
                self.sync_pending(show=bool(alerts))
            if alerts:
                fresh = [a for a in alerts if not a.get('restored',False)]
                if fresh:self.announce(fresh)
            if alerts or changed:
                self.pet.agenda_changed.emit()
            if now >= self.day_check:
                self.day_check = now+30
                day = datetime.now().date()
                if day != self.day:
                    self.day = day; self.pet.agenda_changed.emit()
        except Exception:
            # A temporary storage failure must not disable existing reminders.
            logging.exception('Agenda notification check')
            self.retry_at = now+60

    def refresh(self):
        if self.closed:return
        self.retry_at = 0.
        self.model.invalidate()
        self.revision = self.model.revision
        self.sync_pending()

    def sync_pending(self,show=False):
        pending = [a for a in self.model.pending_alerts() if a['state']=='pending']
        active = {a['id'] for a in pending}
        self.ringing.intersection_update(active)
        if not self.ringing:self.stop_ring()
        tag = getattr(self.pet.speech,'current_tag',None)
        if isinstance(tag,str) and tag.startswith('agenda:') and tag[7:] not in active:
            self.pet.speech.stop(announce=False)
        if show or (self.card and self.card.isVisible()):self.present(pending)

    def present(self,alerts=None):
        if alerts is None:alerts = [a for a in self.model.pending_alerts() if a['state']=='pending']
        alerts = sorted(alerts,key=lambda alert:(alert['kind']!='alarm',-alert['due_at'],alert['id']))
        if alerts and self.card is None:self.card = AgendaCard(self)
        if self.card:self.card.present(alerts)

    def sound_allowed(self):
        sound = self.pet.sound
        return sound.enabled and sound.volume > 0 and time.time() >= sound.quiet_until

    def announce(self,alerts):
        alarms = [a for a in alerts if a['kind']=='alarm' and a.get('sound',True)]
        if alarms:self.start_ring(alarms)
        elif any(a.get('sound',True) for a in alerts):self.pet.sound.play('reminder')
        spoken = [a for a in alerts if a.get('voice',True)]
        if spoken:
            first = spoken[0]
            text = first['title']
            if len(spoken)>1:text += f'. Altri {len(spoken)-1} avvisi.'
            self.pet.speech.speak(text,category='alarm' if first['kind']=='alarm' else 'calendar',
                                  tag='agenda:'+first['id'])
        self.pet.queue_feedback('reminder','wave')

    def start_ring(self,alerts):
        if not self.sound_allowed():return
        self.ringing.update(a['id'] for a in alerts)
        self.ring_until = time.monotonic()+60
        try:
            if self.effect is None:
                self.pet.sound.prepare()
                if self.pet.sound.effect_type is None:
                    self.stop_ring(); return
                from pathlib import Path
                self.effect = self.pet.sound.effect_type(self)
                self.effect.setSource(QUrl.fromLocalFile(str(Path(__file__).resolve().parent/'assets'/'sounds'/'reminder.wav')))
                self.effect.setLoopCount(-2)  # QSoundEffect.Infinite
            self.effect.setVolume(self.pet.sound.volume)
            self.effect.play()
        except Exception:
            logging.exception('Alarm audio'); self.stop_ring()

    def stop_ring(self):
        self.ringing.clear(); self.ring_until = 0.
        if self.effect:self.effect.stop()

    def _stop_alert(self,ident):
        self.ringing.discard(ident)
        if not self.ringing:self.stop_ring()
        if self.pet.speech.current_tag == 'agenda:'+ident:
            self.pet.speech.stop(announce=False)

    def dismiss(self,ident):
        self._stop_alert(ident)
        try:self.model.dismiss(ident)
        except (sqlite3.Error,OSError):
            logging.exception('Agenda dismissal could not be saved')
            if self.card:self.card.when.setText('Chiusura non salvata. Riprova.')
            return
        self.present(); self.pet.agenda_changed.emit()

    def snooze(self,ident):
        self._stop_alert(ident)
        try:self.model.snooze(ident)
        except (sqlite3.Error,OSError):
            logging.exception('Agenda snooze could not be saved')
            if self.card:self.card.when.setText('Rinvio non salvato. Riprova.')
            return
        except ValueError:
            # The series may have been removed or superseded while this card
            # was on screen. Reconcile it rather than throwing from a Qt slot.
            self.present(); return
        self.present(); self.pet.agenda_changed.emit()

    def shutdown(self):
        self.closed = True; self.stop_ring()
        if self.card:self.card.hide()
