# SPDX-License-Identifier: GPL-3.0-or-later
"""Reusable alarm editor and compact native alarm cards."""
from datetime import date, datetime
import logging
import sqlite3
from PyQt6.QtCore import Qt, QDate, QTime
from PyQt6.QtWidgets import (QWidget,QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,
    QLineEdit,QTimeEdit,QDateEdit,QComboBox,QSpinBox,QCheckBox,QDialogButtonBox,
    QSizePolicy,QFrame,QMessageBox)
from yun_jin_ui import STYLE,button,icon_button,plain_label,scroll_page
from yun_jin_dialogs import exec_dialog,owner_window,Messages
from yun_jin_calendar_ui import WeekdayPicker,SHORT_DAYS,agenda_store,notify_changed,AlertHistory,exec_editor


def alarm_repeat_label(alarm):
    days=alarm.get('weekdays')
    if days is None:
        chosen=alarm.get('on_date')
        return datetime.fromisoformat(chosen).strftime('%d/%m/%Y') if chosen else 'Una volta'
    if days==list(range(7)):return 'Ogni giorno'
    if days==list(range(5)):return 'Lun–Ven'
    if days==[5,6]:return 'Sab–Dom'
    return ', '.join(SHORT_DAYS[d] for d in days)


def next_label(alarm,now=None):
    if not alarm.get('enabled'):return 'Disattivata'
    stamp=alarm.get('next_at')
    if stamp is None:return 'Terminata'
    moment=datetime.fromtimestamp(stamp);now=now or datetime.now();days=(moment.date()-now.date()).days
    when='Oggi' if days==0 else 'Domani' if days==1 else moment.strftime('%d/%m')
    return f'{when} alle {moment:%H:%M}'


class AlarmDialog(QDialog):
    def __init__(self,pet,parent=None,alarm=None):
        super().__init__(owner_window(parent));self.pet=pet;self.alarm=alarm;self.saved_id=None
        self.setWindowTitle('Modifica sveglia' if alarm else 'Nuova sveglia');self.setWindowIcon(pet.windowIcon())
        self.setStyleSheet(STYLE);self.resize(465,430)
        data=alarm or {};outer=QVBoxLayout(self);outer.setContentsMargins(20,18,20,18);outer.setSpacing(12)
        content=QWidget();layout=QVBoxLayout(content);layout.setContentsMargins(0,0,4,0);layout.setSpacing(14)
        self.title=QLineEdit(data.get('title',''));self.title.setPlaceholderText('Nome (facoltativo)');self.title.setMaxLength(200)
        self.title.setAccessibleName('Nome sveglia');layout.addWidget(self.title)
        hero=QFrame();hero.setObjectName('hero');hbox=QHBoxLayout(hero);hbox.setContentsMargins(14,12,14,12);hbox.addStretch()
        self.clock=QTimeEdit(QTime.fromString(data.get('clock','08:00'),'HH:mm'));self.clock.setDisplayFormat('HH:mm')
        self.clock.setAccessibleName('Ora sveglia');self.clock.setMinimumWidth(200)
        self.clock.setStyleSheet('QTimeEdit {font-size:42px; font-weight:300; background:transparent; border:none; padding:4px 24px 4px 8px;}')
        hbox.addWidget(self.clock);hbox.addStretch();layout.addWidget(hero)
        form=QFormLayout();form.setHorizontalSpacing(14);form.setVerticalSpacing(12)
        self.repeat=QComboBox();self.repeat.setAccessibleName('Ripetizione sveglia')
        for label,key in [('Una volta','once'),('Ogni giorno','daily'),('Lunedì–venerdì','weekdays'),('Fine settimana','weekend'),('Giorni specifici','custom'),('In una data','date')]:
            self.repeat.addItem(label,key)
        form.addRow('Ripeti',self.repeat);layout.addLayout(form)
        days=data.get('weekdays');kind='once'
        if days==list(range(7)):kind='daily'
        elif days==list(range(5)):kind='weekdays'
        elif days==[5,6]:kind='weekend'
        elif days:kind='custom'
        elif data.get('on_date'):kind='date'
        self.repeat.setCurrentIndex(self.repeat.findData(kind))
        self.days=WeekdayPicker(days or [date.today().weekday()]);layout.addWidget(self.days)
        chosen=date.fromisoformat(data['on_date']) if data.get('on_date') else date.today()
        self.on_date=QDateEdit(QDate(chosen.year,chosen.month,chosen.day));self.on_date.setCalendarPopup(True)
        self.on_date.setDisplayFormat('dd/MM/yyyy');self.on_date.setAccessibleName('Data sveglia');layout.addWidget(self.on_date)
        row=QHBoxLayout();row.setSpacing(12);row.addWidget(plain_label('Rimanda di'))
        self.snooze=QSpinBox();self.snooze.setRange(1,120);self.snooze.setValue(data.get('snooze_minutes',10));self.snooze.setSuffix(' min')
        self.snooze.setAccessibleName('Minuti del rinvio');row.addWidget(self.snooze);row.addStretch();layout.addLayout(row)
        outputs=QHBoxLayout();outputs.setSpacing(22)
        self.sound=QCheckBox('Suono');self.sound.setChecked(data.get('sound',True));outputs.addWidget(self.sound)
        self.voice=QCheckBox('Leggi l’avviso');self.voice.setChecked(data.get('voice',True));outputs.addWidget(self.voice);outputs.addStretch()
        layout.addLayout(outputs);layout.addStretch();outer.addWidget(scroll_page(content),1)
        self.error=plain_label('','alert');self.error.hide();outer.addWidget(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('Salva');buttons.button(QDialogButtonBox.StandardButton.Save).setProperty('role','primary')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Annulla');buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);outer.addWidget(buttons)
        self.repeat.currentIndexChanged.connect(self.update_controls);self.update_controls();self.clock.setFocus()
    def update_controls(self,*_):
        key=self.repeat.currentData();self.days.setVisible(key=='custom');self.on_date.setVisible(key=='date')
    def payload(self):
        key=self.repeat.currentData()
        days={'daily':list(range(7)),'weekdays':list(range(5)),'weekend':[5,6]}.get(key)
        if key=='custom':
            days=self.days.selected()
            if not days:raise ValueError('Scegli almeno un giorno della settimana.')
        return dict(title=self.title.text().strip() or 'Sveglia',clock=self.clock.time().toString('HH:mm'),
                    weekdays=days,on_date=self.on_date.date().toString('yyyy-MM-dd') if key=='date' else None,
                    enabled=self.alarm.get('enabled',True) if self.alarm else True,
                    snooze_minutes=self.snooze.value(),sound=self.sound.isChecked(),voice=self.voice.isChecked())
    def save(self):
        try:
            self.saved_id=agenda_store(self.pet).save_alarm(**self.payload(),alarm_id=self.alarm['id'] if self.alarm else None)
        except (ValueError,TypeError) as exc:
            self.error.setText(str(exc));self.error.show();return
        except (sqlite3.Error,OSError):
            logging.exception('Save alarm');self.error.setText('Salvataggio non riuscito. Riprova.');self.error.show();return
        notify_changed(self.pet);self.accept()


class AlarmsPanel(QWidget):
    def __init__(self,pet):
        super().__init__();self.pet=pet;self.store=agenda_store(pet);self.cards={};self.visible_alarm_limit=30
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(14)
        tools=QHBoxLayout();tools.setSpacing(12);button('Nuova sveglia',self.new_alarm,tools,glyph='plus',role='primary');tools.addStretch();root.addLayout(tools)
        self.history=AlertHistory(pet,'alarm',self.open_alert);root.addWidget(self.history)
        content=QWidget();self.list_layout=QVBoxLayout(content);self.list_layout.setContentsMargins(0,0,4,0);self.list_layout.setSpacing(12)
        root.addWidget(scroll_page(content),1)
        signal=getattr(pet,'agenda_changed',None)
        if signal is not None and hasattr(signal,'connect'):signal.connect(self.refresh_if_visible)
        self.refresh()
    def showEvent(self,event):super().showEvent(event);self.refresh()
    def refresh_if_visible(self,*_):
        if self.isVisible():self.refresh()
    def refresh(self):
        self.history.refresh()
        while self.list_layout.count():
            item=self.list_layout.takeAt(0)
            if item.widget():item.widget().hide();item.widget().deleteLater()
        self.cards={};alarms=self.store.alarms()
        if not alarms:
            hero=QFrame();hero.setObjectName('hero');layout=QVBoxLayout(hero);layout.setContentsMargins(24,32,24,32);layout.setSpacing(12)
            label=plain_label('Nessuna sveglia','muted');label.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(label)
            self.list_layout.addWidget(hero)
        for alarm in alarms[:self.visible_alarm_limit]:
            frame=QFrame();frame.setObjectName('card');frame.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Fixed);layout=QHBoxLayout(frame);layout.setContentsMargins(18,14,16,14);layout.setSpacing(12)
            info=QVBoxLayout();info.setSpacing(5);layout.addLayout(info,1)
            clock=button(alarm['clock'],lambda checked=False,row=alarm:self.edit_alarm(row),role='quiet')
            clock.setAccessibleName('Modifica sveglia delle '+alarm['clock']);clock.setStyleSheet('QPushButton {font-size:35px;font-weight:300;text-align:left;padding:0;border:none;}')
            clock.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed);info.addWidget(clock)
            if alarm['title'] and alarm['title']!='Sveglia':
                title=plain_label(alarm['title'],'section');title.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred);info.addWidget(title)
            info.addWidget(plain_label(alarm_repeat_label(alarm),'muted'))
            next_time=plain_label(next_label(alarm),'muted');next_time.setStyleSheet('font-size:11px;');info.addWidget(next_time)
            side=QVBoxLayout();side.setSpacing(8);layout.addLayout(side)
            toggle=QCheckBox('Attiva');toggle.setChecked(alarm.get('enabled',False));toggle.setAccessibleName('Attiva sveglia delle '+alarm['clock'])
            toggle.toggled.connect(lambda enabled,ident=alarm['id']:self.toggle_alarm(ident,enabled));side.addWidget(toggle)
            actions=QHBoxLayout();actions.setSpacing(4)
            icon_button('settings','Modifica sveglia',lambda checked=False,row=alarm:self.edit_alarm(row),actions)
            icon_button('trash','Elimina sveglia',lambda checked=False,row=alarm:self.delete_alarm(row),actions)
            side.addLayout(actions);side.addStretch();self.list_layout.addWidget(frame)
            self.cards[alarm['id']]={'frame':frame,'toggle':toggle,'next':next_time,'clock':clock}
        if len(alarms)>self.visible_alarm_limit:
            self.list_layout.addWidget(button(f'Mostra altre ({len(alarms)-self.visible_alarm_limit})',self.more_alarms,role='quiet'))
        self.list_layout.addStretch()
    def more_alarms(self):
        self.visible_alarm_limit+=30;self.refresh()
    def open_alert(self,row):
        alarm=self.store.get(row['item_id'])
        if alarm:self.edit_alarm(alarm)
    def new_alarm(self):self.edit_alarm()
    def edit_alarm(self,alarm=None):
        dialog=AlarmDialog(self.pet,self,alarm)
        if exec_editor(dialog,self.pet)==QDialog.DialogCode.Accepted:self.refresh()
    def toggle_alarm(self,ident,enabled):
        try:self.store.set_enabled(ident,enabled)
        except ValueError as exc:
            Messages.warning(self,'Sveglia',str(exc));self.refresh();return
        notify_changed(self.pet);self.refresh()
    def delete_alarm(self,alarm):
        if Messages.question(self,'Elimina sveglia',f'Eliminare la sveglia «{alarm["title"]}» delle {alarm["clock"]}?')!=QMessageBox.StandardButton.Yes:return
        self.store.delete(alarm['id']);notify_changed(self.pet);self.refresh()
