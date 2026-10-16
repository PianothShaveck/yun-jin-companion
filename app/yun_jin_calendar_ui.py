# SPDX-License-Identifier: GPL-3.0-or-later
"""Calendar with native controls, bounded illustrations and no background polling."""
from collections import OrderedDict
from datetime import date, datetime, time, timedelta
from pathlib import Path
import logging
import sqlite3

from PyQt6 import sip
from PyQt6.QtCore import Qt, QDate, QTime, QSize, QRectF, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QFont, QLinearGradient, QImageReader, QPixmap
from PyQt6.QtWidgets import (QWidget, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QBoxLayout, QFormLayout, QLabel, QPushButton, QComboBox, QSpinBox, QCheckBox,
    QLineEdit, QTextEdit, QDateEdit, QTimeEdit, QDialogButtonBox, QSizePolicy,
    QFrame, QMessageBox, QLayout)
from yun_jin_ui import STYLE, button, icon_button, plain_label, scroll_page
from yun_jin_dialogs import exec_dialog, show_dialog, owner_window, Messages

MONTHS = ('Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno','Luglio','Agosto',
          'Settembre','Ottobre','Novembre','Dicembre')
WEEKDAYS = ('Lunedì','Martedì','Mercoledì','Giovedì','Venerdì','Sabato','Domenica')
SHORT_DAYS = ('Lun','Mar','Mer','Gio','Ven','Sab','Dom')
COLORS = {'rose':'#e4b2ce','lavender':'#c8b4e5','blue':'#b6c8eb','teal':'#a9d3d5','amber':'#e5bb94'}


def event_color(row):
    value=row.get('color','rose')
    return COLORS.get(value,value if isinstance(value,str) and value.startswith('#') else COLORS['rose'])


def agenda_store(pet):
    service = getattr(pet.store, 'agenda', None)
    if service is None:
        from yun_jin_agenda import AgendaStore
        service = AgendaStore(pet.store)
        pet.store.agenda = service
    return service


def notify_changed(pet):
    """Also refresh the scheduler after a save, without adding a page timer."""
    signal = getattr(pet, 'agenda_changed', None)
    if signal is not None and hasattr(signal, 'emit'):
        signal.emit()
    callback = getattr(pet, 'refresh_agenda', None)
    if callable(callback):
        callback()


def exec_editor(dialog,pet):
    """All page/global entry points share one editor and preserve unfinished input."""
    active=getattr(pet,'agenda_editor',None)
    if active is not None and not sip.isdeleted(active) and active is not dialog:
        show_dialog(active,pet);dialog.deleteLater();return QDialog.DialogCode.Rejected
    pet.agenda_editor=dialog
    try:return exec_dialog(dialog,pet)
    finally:
        if getattr(pet,'agenda_editor',None) is dialog:pet.agenda_editor=None
        dialog.deleteLater()


def parse_local(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time())
    return datetime.fromisoformat(str(value))


def qdate(value):
    value = parse_local(value).date()
    return QDate(value.year, value.month, value.day)


def local_day_label(day, year=False):
    return f'{WEEKDAYS[day.weekday()]} {day.day} {MONTHS[day.month-1].lower()}' + (f' {day.year}' if year else '')


def recurrence_label(recurrence):
    if not recurrence:
        return ''
    every = recurrence.get('interval', 1)
    freq = recurrence.get('frequency')
    if freq == 'weekly':
        days = recurrence.get('weekdays') or []
        if every == 1 and days == list(range(7)):
            return 'Ogni giorno'
        if every == 1 and days == list(range(5)):
            return 'Lun–Ven'
        names = ', '.join(SHORT_DAYS[d] for d in days)
        return (names if every == 1 and names else ('Ogni settimana' if every == 1 else f'Ogni {every} settimane'))
    if freq == 'daily':
        return 'Ogni giorno' if every == 1 else f'Ogni {every} giorni'
    if freq == 'monthly':
        return 'Ogni mese' if every == 1 else f'Ogni {every} mesi'
    return 'Ogni anno' if every == 1 else f'Ogni {every} anni'


class WeekdayPicker(QWidget):
    changed = pyqtSignal()
    def __init__(self, selected=(), parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self); row.setContentsMargins(0,0,0,0); row.setSpacing(5)
        self.buttons = []
        for i, label in enumerate(SHORT_DAYS):
            b = QPushButton(label); b.setCheckable(True); b.setChecked(i in selected)
            b.setAutoDefault(False); b.setAccessibleName(WEEKDAYS[i]); b.setMinimumWidth(34)
            b.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            b.setStyleSheet('QPushButton {padding:6px 2px;} QPushButton:checked {background:#695477;border-color:#ba9cca;color:white;}')
            b.toggled.connect(self.changed); row.addWidget(b); self.buttons.append(b)
    def selected(self):
        return [i for i,b in enumerate(self.buttons) if b.isChecked()]
    def set_selected(self, days):
        for i,b in enumerate(self.buttons): b.setChecked(i in days)


class RecurrenceEditor(QWidget):
    def __init__(self, start, recurrence=None, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Maximum)
        recurrence = recurrence or {}
        layout = QVBoxLayout(self); layout.setContentsMargins(0,0,0,0); layout.setSpacing(10)
        row = QHBoxLayout(); row.setSpacing(10)
        self.frequency = QComboBox(); self.frequency.setAccessibleName('Ripetizione')
        for label,key in [('Non ripetere',None),('Ogni giorno','daily'),('Ogni settimana','weekly'),('Ogni mese','monthly'),('Ogni anno','yearly')]:
            self.frequency.addItem(label,key)
        self.frequency.setCurrentIndex(max(0,self.frequency.findData(recurrence.get('frequency'))))
        row.addWidget(self.frequency,1)
        self.interval = QSpinBox(); self.interval.setRange(1,999); self.interval.setPrefix('Ogni ')
        self.interval.setValue(recurrence.get('interval',1)); self.interval.setAccessibleName('Intervallo di ripetizione')
        row.addWidget(self.interval); layout.addLayout(row)
        self.days = WeekdayPicker(recurrence.get('weekdays',[start.weekday()]))
        layout.addWidget(self.days)
        self.ending = QWidget(); endrow = QHBoxLayout(self.ending); endrow.setContentsMargins(0,0,0,0); endrow.setSpacing(10)
        endrow.addWidget(plain_label('Termina'))
        self.end_mode = QComboBox(); self.end_mode.setAccessibleName('Fine ripetizione')
        self.end_mode.addItems(['Mai','Il giorno','Dopo']); endrow.addWidget(self.end_mode,1)
        self.until = QDateEdit(qdate(recurrence.get('until') or start + timedelta(days=365)))
        self.until.setCalendarPopup(True); self.until.setDisplayFormat('dd/MM/yyyy'); self.until.setAccessibleName('Ultimo giorno della serie')
        self.count = QSpinBox(); self.count.setRange(1,10000); self.count.setSuffix(' volte'); self.count.setValue(recurrence.get('count',10))
        self.count.setAccessibleName('Numero di ripetizioni')
        endrow.addWidget(self.until); endrow.addWidget(self.count); layout.addWidget(self.ending)
        if recurrence.get('until'): self.end_mode.setCurrentIndex(1)
        elif recurrence.get('count'): self.end_mode.setCurrentIndex(2)
        self.frequency.currentIndexChanged.connect(self.update_controls); self.end_mode.currentIndexChanged.connect(self.update_controls)
        self.update_controls()
    def update_controls(self,*_):
        freq = self.frequency.currentData()
        self.interval.setVisible(freq is not None); self.ending.setVisible(freq is not None)
        self.days.setVisible(freq == 'weekly')
        self.until.setVisible(self.end_mode.currentIndex() == 1)
        self.count.setVisible(self.end_mode.currentIndex() == 2)
        self.interval.setSuffix({'daily':' giorni','weekly':' settimane','monthly':' mesi','yearly':' anni'}.get(freq,''))
    def value(self):
        freq = self.frequency.currentData()
        if freq is None: return None
        result = dict(frequency=freq,interval=self.interval.value())
        if freq == 'weekly':
            result['weekdays'] = self.days.selected()
            if not result['weekdays']: raise ValueError('Scegli almeno un giorno della settimana.')
        if self.end_mode.currentIndex() == 1: result['until'] = self.until.date().toString('yyyy-MM-dd')
        elif self.end_mode.currentIndex() == 2: result['count'] = self.count.value()
        return result


class EventDialog(QDialog):
    def __init__(self, pet, parent=None, day=None, event=None, occurrence=None, scope='series'):
        super().__init__(owner_window(parent))
        self.pet=pet; self.event=event; self.occurrence=occurrence; self.scope=scope; self.saved_id=None
        self.setWindowTitle('Modifica impegno' if event else 'Nuovo impegno'); self.setWindowIcon(pet.windowIcon())
        self.setStyleSheet(STYLE); self.resize(540,570)
        now=datetime.now(); day=day or now.date()
        source = occurrence if occurrence is not None and scope == 'occurrence' else event
        source = source or {}
        default_start=(now.replace(second=0,microsecond=0)+timedelta(minutes=30-now.minute%30)) if day==now.date() else datetime.combine(day,time(9))
        start=parse_local(source['start_local']) if source else default_start
        end=parse_local(source.get('end_local') or start+timedelta(hours=1))
        is_all_day=bool(source.get('all_day',False))
        if is_all_day: end-=timedelta(days=1)
        outer=QVBoxLayout(self); outer.setContentsMargins(20,18,20,18); outer.setSpacing(12)
        content=QWidget(); layout=QVBoxLayout(content); layout.setContentsMargins(0,0,4,0); layout.setSpacing(12)
        self.title=QLineEdit(source.get('title','')); self.title.setPlaceholderText('Titolo'); self.title.setMaxLength(200)
        self.title.setAccessibleName('Titolo impegno'); layout.addWidget(self.title)
        self.all_day=QCheckBox('Tutto il giorno'); self.all_day.setChecked(is_all_day); layout.addWidget(self.all_day)
        form=QFormLayout(); form.setHorizontalSpacing(15); form.setVerticalSpacing(10)
        self.start_date=QDateEdit(qdate(start)); self.start_date.setAccessibleName('Data inizio')
        self.end_date=QDateEdit(qdate(end)); self.end_date.setAccessibleName('Data fine')
        self.start_time=QTimeEdit(QTime(start.hour,start.minute)); self.start_time.setAccessibleName('Ora inizio')
        self.end_time=QTimeEdit(QTime(end.hour,end.minute)); self.end_time.setAccessibleName('Ora fine')
        for edit in (self.start_date,self.end_date):edit.setCalendarPopup(True);edit.setDisplayFormat('dd/MM/yyyy')
        for edit in (self.start_time,self.end_time):edit.setDisplayFormat('HH:mm')
        for label,d,t in [('Inizio',self.start_date,self.start_time),('Fine',self.end_date,self.end_time)]:
            row=QHBoxLayout();row.setSpacing(10);row.addWidget(d,1);row.addWidget(t);form.addRow(label,row)
        layout.addLayout(form)
        self.recurrence=RecurrenceEditor(start.date(),source.get('recurrence'));layout.addWidget(self.recurrence)
        self.recurrence.setVisible(scope!='occurrence')
        alert=QHBoxLayout();alert.setSpacing(12);alert.addWidget(plain_label('Avviso'))
        self.reminder=QComboBox();self.reminder.setAccessibleName('Anticipo avviso')
        for label,minutes in [('Nessuno',None),('All’inizio',0),('5 minuti prima',5),('10 minuti prima',10),('15 minuti prima',15),('30 minuti prima',30),('1 ora prima',60),('1 giorno prima',1440)]:
            self.reminder.addItem(label,minutes)
        minutes=source.get('reminder_minutes',10)
        if minutes is not None and self.reminder.findData(minutes)<0:self.reminder.addItem(f'{minutes} minuti prima',minutes)
        self.reminder.setCurrentIndex(max(0,self.reminder.findData(minutes)))
        self._previous_all_day=is_all_day;self._reminder_touched=False;self._timed_reminder=minutes
        self.reminder.activated.connect(lambda *_:setattr(self,'_reminder_touched',True))
        alert.addWidget(self.reminder,1);layout.addLayout(alert)
        self.voice=QCheckBox('Leggi l’avviso');self.voice.setChecked(source.get('voice',True));layout.addWidget(self.voice)
        self.reminder.currentIndexChanged.connect(lambda *_:self.voice.setEnabled(self.reminder.currentData() is not None))
        self.voice.setEnabled(self.reminder.currentData() is not None)
        self.details=QTextEdit();self.details.setAcceptRichText(False);self.details.setPlainText(source.get('details',''))
        self.details.setPlaceholderText('Note');self.details.setAccessibleName('Note impegno');self.details.setMaximumHeight(94);layout.addWidget(self.details)
        self.timezone=source.get('timezone','') or (event or {}).get('timezone','')
        self.color=source.get('color',(event or {}).get('color','rose'))
        if self.timezone:layout.addWidget(plain_label(self.timezone,'muted'))
        layout.addStretch()
        outer.addWidget(scroll_page(content),1)
        self.error=plain_label('','alert');self.error.hide();outer.addWidget(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('Salva');buttons.button(QDialogButtonBox.StandardButton.Save).setProperty('role','primary')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Annulla')
        buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);outer.addWidget(buttons)
        self.all_day.toggled.connect(self.update_times);self.update_times();self.title.setFocus()
        self._start_anchor=datetime.combine(self.start_date.date().toPyDate(),self.start_time.time().toPyTime())
        self.start_date.dateChanged.connect(self.shift_end);self.start_time.timeChanged.connect(self.shift_end)
    def update_times(self,*_):
        all_day=self.all_day.isChecked()
        for edit in (self.start_time,self.end_time):edit.setVisible(not all_day)
        if all_day!=self._previous_all_day and not self._reminder_touched:
            if all_day:
                self._timed_reminder=self.reminder.currentData();self.reminder.setCurrentIndex(self.reminder.findData(None))
            else:self.reminder.setCurrentIndex(max(0,self.reminder.findData(self._timed_reminder)))
        self.reminder.setItemText(self.reminder.findData(0),'A mezzanotte' if all_day else 'All’inizio')
        self._previous_all_day=all_day
    def shift_end(self,*_):
        start=datetime.combine(self.start_date.date().toPyDate(),self.start_time.time().toPyTime())
        delta=start-self._start_anchor;self._start_anchor=start
        end=datetime.combine(self.end_date.date().toPyDate(),self.end_time.time().toPyTime())
        try:end+=delta
        except OverflowError:return
        self.end_date.setDate(qdate(end));self.end_time.setTime(QTime(end.hour,end.minute))

    def payload(self):
        title=self.title.text().strip()
        if len(self.details.toPlainText())>4000:raise ValueError('Le note possono contenere al massimo 4000 caratteri.')
        if not title:raise ValueError('Il titolo non può essere vuoto.')
        start=self.start_date.date().toPyDate();end=self.end_date.date().toPyDate()
        if self.all_day.isChecked():
            if end<start:raise ValueError('La fine deve essere dopo l’inizio.')
            start_local=start.isoformat();end_local=(end+timedelta(days=1)).isoformat()
        else:
            start=datetime.combine(start,self.start_time.time().toPyTime());end=datetime.combine(end,self.end_time.time().toPyTime())
            if end<=start:raise ValueError('La fine deve essere dopo l’inizio.')
            start_local=start.isoformat(timespec='seconds');end_local=end.isoformat(timespec='seconds')
        recurrence=self.recurrence.value() if self.scope!='occurrence' else None
        if recurrence and recurrence.get('until','9999-12-31')<start_local[:10]:
            raise ValueError('La serie non può terminare prima dell’inizio.')
        return dict(title=title,start=start_local,end=end_local,all_day=self.all_day.isChecked(),
                    recurrence=recurrence,reminder_minutes=self.reminder.currentData(),voice=self.voice.isChecked(),
                    details=self.details.toPlainText().strip(),timezone=self.timezone,color=self.color,enabled=(self.event or {}).get('enabled',True))
    def save(self):
        try:
            data=self.payload();store=agenda_store(self.pet)
            if self.scope=='occurrence' and self.event and self.occurrence:
                data.pop('recurrence');data.pop('timezone');data.pop('enabled');data['start_local']=data.pop('start');data['end_local']=data.pop('end')
                store.save_exception(self.event['id'],self.occurrence['occurrence_key'],**data);self.saved_id=self.event['id']
            else:self.saved_id=store.save_event(**data,event_id=self.event['id'] if self.event else None)
        except (ValueError,TypeError) as exc:
            self.error.setText(str(exc));self.error.show();return
        except (sqlite3.Error,OSError):
            logging.exception('Save calendar event');self.error.setText('Salvataggio non riuscito. Riprova.');self.error.show();return
        notify_changed(self.pet);self.accept()


class ScopeDialog(QDialog):
    def __init__(self,pet,parent,deleting=False):
        super().__init__(owner_window(parent));self.pet=pet;self.scope=None;self.setStyleSheet(STYLE)
        self.setWindowTitle('Elimina impegno' if deleting else 'Modifica impegno');self.setWindowIcon(pet.windowIcon())
        layout=QVBoxLayout(self);layout.setContentsMargins(20,20,20,20);layout.setSpacing(12)
        layout.addWidget(plain_label('Quali impegni vuoi eliminare?' if deleting else 'Quali impegni vuoi modificare?'))
        row=QHBoxLayout();row.setSpacing(10);layout.addLayout(row)
        button('Solo questo',lambda:self.choose('occurrence'),row,role='primary')
        button('Tutta la serie',lambda:self.choose('series'),row)
        button('Annulla',self.reject,row)
    def choose(self,scope):self.scope=scope;self.accept()


class MonthJumpDialog(QDialog):
    def __init__(self,pet,parent,day):
        super().__init__(owner_window(parent));self.pet=pet;self.setStyleSheet(STYLE);self.setWindowTitle('Vai al mese')
        self.setWindowIcon(pet.windowIcon());layout=QVBoxLayout(self);layout.setContentsMargins(20,20,20,20)
        row=QHBoxLayout();self.month=QComboBox();self.month.addItems(MONTHS);self.month.setCurrentIndex(day.month-1)
        self.month.setAccessibleName('Mese');self.year=QSpinBox();self.year.setRange(1900,9998);self.year.setValue(day.year)
        self.year.setAccessibleName('Anno');row.addWidget(self.month);row.addWidget(self.year);layout.addLayout(row)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Vai');buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Annulla')
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
    def value(self):return date(self.year.value(),self.month.currentIndex()+1,1)


class IllustrationCanvas(QWidget):
    def __init__(self,path):
        super().__init__();reader=QImageReader(str(path));reader.setAutoTransform(True)
        size=reader.size()
        if size.isValid() and size.width()*size.height()>16_000_000:
            reader.setScaledSize(size.scaled(QSize(4096,4096),Qt.AspectRatioMode.KeepAspectRatio))
        self.pixmap=QPixmap.fromImage(reader.read());self.setMinimumSize(180,120)
        self.setAccessibleName('Illustrazione del calendario')
    def image_rect(self):
        if self.pixmap.isNull():return QRectF()
        size=self.pixmap.size();scale=min(self.width()/size.width(),self.height()/size.height())
        width=size.width()*scale;height=size.height()*scale
        return QRectF((self.width()-width)/2,(self.height()-height)/2,width,height)
    def paintEvent(self,event):
        if self.pixmap.isNull():return
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(self.image_rect(),self.pixmap,QRectF(self.pixmap.rect()));painter.end()


class IllustrationDialog(QDialog):
    def __init__(self,pet,parent,path,day):
        super().__init__(owner_window(parent));self.pet=pet;self.setWindowIcon(pet.windowIcon());self.setStyleSheet(STYLE)
        self.setWindowTitle(f'{MONTHS[day.month-1]} {day.year} · Yun Jin')
        layout=QVBoxLayout(self);layout.setContentsMargins(10,10,10,10)
        controls=QHBoxLayout();controls.addStretch()
        self.close_button=icon_button('close','Chiudi',self.reject,controls)
        layout.addLayout(controls)
        self.canvas=IllustrationCanvas(path);layout.addWidget(self.canvas)
        available=self.screen().availableGeometry()
        self.resize(min(1100,max(240,available.width()-80)),min(760,max(180,available.height()-100)))
    def done(self,result):
        # Release the full-size pixels as soon as it closes, even before Qt's
        # deferred deletion gets its next event-loop turn.
        self.canvas.pixmap=QPixmap();super().done(result)


class CalendarHero(QWidget):
    """Decode just the displayed scene; cache two small pixel buffers at most."""
    illustration_requested=pyqtSignal(object)
    def __init__(self):
        super().__init__();self.day=date.today();self.cache=OrderedDict();self.path=None;self.pixmap=None
        self.setMinimumHeight(160);self.setMaximumHeight(190);self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        self.setAccessibleName('Illustrazione del mese')
        layout=QVBoxLayout(self);layout.setContentsMargins(22,15,12,15);layout.setSpacing(8)
        self.month_button=button('',None,role='quiet');self.month_button.setAccessibleName('Scegli mese e anno')
        self.month_button.setStyleSheet('QPushButton {font-size:27px;font-weight:600;text-align:left;padding:2px 0;border:none;background:transparent;} QPushButton:hover {color:#ffffff;}')
        self.month_button.setSizePolicy(QSizePolicy.Policy.Fixed,QSizePolicy.Policy.Fixed)
        layout.addWidget(self.month_button);layout.addStretch()
        self.tools=QHBoxLayout();self.tools.setSpacing(3)
        layout.addLayout(self.tools)
        self.open_art=QPushButton('',self);self.open_art.setAutoDefault(False)
        self.open_art.setAccessibleName('Apri illustrazione');self.open_art.setToolTip('Apri illustrazione')
        self.open_art.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_art.setStyleSheet('QPushButton {background:transparent;border:0;padding:0;min-height:0;} QPushButton:focus {border:1px solid #d7c2df;border-radius:7px;}')
        self.open_art.clicked.connect(lambda:self.illustration_requested.emit(self.path) if self.path else None)
        self.open_art.hide()

    def image_rect(self):
        if self.pixmap is None:return QRectF()
        size=self.pixmap.size();area=QRectF(self.width()*0.46,0,self.width()*0.54,self.height())
        scale=min(area.width()/size.width(),area.height()/size.height())
        width=size.width()*scale;height=size.height()*scale
        return QRectF(area.center().x()-width/2,area.center().y()-height/2,width,height)
    def position_art_button(self):
        self.open_art.setVisible(self.pixmap is not None)
        if self.pixmap is not None:self.open_art.setGeometry(self.image_rect().toAlignedRect());self.open_art.raise_()
    def resizeEvent(self,event):
        super().resizeEvent(event);self.position_art_button()

    def set_month(self,day):
        self.day=day;self.path=None;self.pixmap=None
        self.month_button.setText(f'{MONTHS[day.month-1]}\n{day.year}')
        try:
            from yun_jin_calendar_art import illustration_for
            path=illustration_for(day.year,day.month)
        except (ImportError,OSError,ValueError,TypeError):path=None
        if path:
            path=Path(path);self.path=path
            if path in self.cache:self.pixmap=self.cache.pop(path);self.cache[path]=self.pixmap
            else:
                reader=QImageReader(str(path));reader.setAutoTransform(True)
                size=reader.size()
                if size.isValid():reader.setScaledSize(size.scaled(QSize(1000,600),Qt.AspectRatioMode.KeepAspectRatio))
                pix=QPixmap.fromImage(reader.read())
                if not pix.isNull():
                    self.pixmap=pix;self.cache[path]=pix
                    while len(self.cache)>2:self.cache.popitem(last=False)
        self.position_art_button();self.update()
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(self.rect());clip=QPainterPath();clip.addRoundedRect(rect,15,15);painter.setClipPath(clip)
        gradient=QLinearGradient(rect.topLeft(),rect.bottomRight());gradient.setColorAt(0,QColor('#42314f'));gradient.setColorAt(1,QColor('#2b4952'))
        painter.fillRect(rect,gradient)
        if self.pixmap is not None:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(self.image_rect(),self.pixmap,QRectF(self.pixmap.rect()))
        painter.end()


class DayButton(QPushButton):
    moved=pyqtSignal(int)
    activated=pyqtSignal()
    month_moved=pyqtSignal(int)
    today_requested=pyqtSignal()
    def __init__(self,day):
        super().__init__();self.day=day;self.current_month=True;self.is_today=False;self.chosen=False;self.events=[]
        self.setAutoDefault(False);self.setMinimumSize(42,39);self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor);self.setStyleSheet('QPushButton {padding:0;border:0;background:transparent;min-height:39px;}')
    def update_day(self,day,current_month,chosen,events):
        self.day=day;self.current_month=current_month;self.is_today=day==date.today();self.chosen=chosen;self.events=events
        text=local_day_label(day,True);self.setAccessibleName(text+(f', {len(events)} impegni' if events else ''))
        self.setToolTip('\n'.join([text]+[row['title'] for row in events[:5]]));self.setFocusPolicy(Qt.FocusPolicy.StrongFocus if chosen else Qt.FocusPolicy.NoFocus);self.update()
    def keyPressEvent(self,event):
        step={Qt.Key.Key_Left:-1,Qt.Key.Key_Right:1,Qt.Key.Key_Up:-7,Qt.Key.Key_Down:7}.get(event.key())
        if step is not None:self.moved.emit(step);event.accept();return
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter):self.activated.emit();event.accept();return
        if event.key() in (Qt.Key.Key_PageUp,Qt.Key.Key_PageDown):self.month_moved.emit(-1 if event.key()==Qt.Key.Key_PageUp else 1);event.accept();return
        if event.key()==Qt.Key.Key_Home:self.today_requested.emit();event.accept();return
        super().keyPressEvent(event)
    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.activated.emit();event.accept();return
        super().mouseDoubleClickEvent(event)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);rect=QRectF(self.rect()).adjusted(2,2,-2,-2)
        if self.chosen:p.setBrush(QColor('#6d557f'));p.setPen(QPen(QColor('#c9accf'),1));p.drawRoundedRect(rect,8,8)
        elif self.underMouse():p.setBrush(QColor('#393144'));p.setPen(Qt.PenStyle.NoPen);p.drawRoundedRect(rect,8,8)
        elif self.is_today:p.setBrush(QColor('#353847'));p.setPen(QPen(QColor('#82acb2'),1));p.drawRoundedRect(rect,8,8)
        elif not self.current_month:p.setBrush(QColor(20,17,29,80));p.setPen(Qt.PenStyle.NoPen);p.drawRoundedRect(rect,8,8)
        if self.hasFocus():p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(QColor('#b3d0d8'),1.5));p.drawRoundedRect(rect.adjusted(2,2,-2,-2),6,6)
        p.setPen(QColor('#fff9ff' if self.chosen else '#eee6f3' if self.current_month else '#bfb3ca'))
        font=QFont(self.font());font.setPointSizeF(11);font.setBold(self.is_today);p.setFont(font)
        p.drawText(rect.adjusted(0,-4 if self.events else 0,0,0),Qt.AlignmentFlag.AlignCenter,str(self.day.day))
        if self.events:
            n=min(3,len(self.events));start=rect.center().x()-(n-1)*4
            for i in range(n):p.setBrush(QColor(event_color(self.events[i])));p.setPen(Qt.PenStyle.NoPen);p.drawEllipse(QRectF(start+i*8-2,rect.bottom()-8,4,4))
        p.end()


class CalendarBackdrop(QWidget):
    """Reuse the hero's decoded pixels; resize only changes the painted crop."""
    def __init__(self,hero):
        super().__init__();self.hero=hero
    def image_source_rect(self):
        pix=self.hero.pixmap
        if pix is None or pix.isNull() or not self.width() or not self.height():return QRectF()
        width,height=pix.width(),pix.height();scale=max(self.width()/width,self.height()/height)
        shown_width=min(width,self.width()/scale);shown_height=min(height,self.height()/scale)
        return QRectF((width-shown_width)/2,(height-shown_height)/2,shown_width,shown_height)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(self.rect()).adjusted(.5,.5,-.5,-.5)
        clip=QPainterPath();clip.addRoundedRect(rect,14,14);p.setClipPath(clip)
        p.fillRect(rect,QColor('#252131'))
        pix=self.hero.pixmap
        if pix is not None and not pix.isNull():
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform);p.setOpacity(.28)
            p.drawPixmap(QRectF(self.rect()),pix,self.image_source_rect());p.setOpacity(1)
            veil=QLinearGradient(rect.topLeft(),rect.bottomLeft())
            veil.setColorAt(0,QColor(24,20,36,50));veil.setColorAt(1,QColor(24,20,36,20))
            p.fillRect(rect,veil)
        p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(QColor('#51465e'),1))
        p.drawRoundedRect(rect,14,14);p.end()


class AlertHistory(QWidget):
    """Recent unresolved notices, revealed only when there is something to show."""
    def __init__(self,pet,kind,open_item=None):
        super().__init__();self.pet=pet;self.kind=kind;self.open_item=open_item;self.rows=[]
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(8)
        self.toggle=button('',self.expand,root,role='quiet');self.toggle.setCheckable(True)
        self.toggle.setStyleSheet('QPushButton {text-align:left;padding:5px 0;}')
        body=QWidget();self.list_layout=QVBoxLayout(body);self.list_layout.setContentsMargins(0,0,4,0);self.list_layout.setSpacing(6)
        self.list=scroll_page(body);self.list.setMaximumHeight(200);self.list.hide();root.addWidget(self.list)
        self.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Maximum)
    def refresh(self):
        self.rows=[row for row in agenda_store(self.pet).alerts(limit=100) if row['kind']==self.kind]
        self.setVisible(bool(self.rows));self.toggle.setText(f'Avvisi recenti ({len(self.rows)})')
        if self.toggle.isChecked():self.populate()
    def expand(self,*_):
        self.list.setVisible(self.toggle.isChecked())
        if self.toggle.isChecked():self.populate()
    def populate(self):
        while self.list_layout.count():
            item=self.list_layout.takeAt(0)
            if item.widget():item.widget().hide();item.widget().deleteLater()
        for row in self.rows:
            tile=QFrame();tile.setObjectName('card');layout=QHBoxLayout(tile);layout.setContentsMargins(10,7,6,7);layout.setSpacing(10)
            info=QVBoxLayout();info.setSpacing(3);layout.addLayout(info,1)
            title=plain_label(row['title']);title.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred);info.addWidget(title)
            when=datetime.fromtimestamp(row['due_at'] if row['state']=='snoozed' else row['scheduled_at'])
            state={'missed':'Non visto','pending':'Da gestire','snoozed':'Rimandato'}[row['state']]
            label=plain_label(f'{when:%d/%m · %H:%M} · {state}','muted');label.setStyleSheet('font-size:11px;');info.addWidget(label)
            if self.open_item:icon_button('calendar' if self.kind=='event' else 'alarm','Apri impegno' if self.kind=='event' else 'Apri sveglia',lambda checked=False,r=row:self.open_item(r),layout)
            icon_button('check','Chiudi avviso',lambda checked=False,ident=row['id']:self.dismiss(ident),layout)
            self.list_layout.addWidget(tile)
        self.list_layout.addStretch()
        self.list.setMinimumHeight(min(200,max(70,len(self.rows)*70)))
    def dismiss(self,ident):
        service=getattr(self.pet,'agenda_service',None)
        if service is not None:service.dismiss(ident)
        else:agenda_store(self.pet).dismiss(ident);notify_changed(self.pet)
        self.refresh()


class CalendarPanel(QWidget):
    def __init__(self,pet):
        super().__init__();self.pet=pet;self.store=agenda_store(pet);self.selected=date.today();self.month=self.selected.replace(day=1)
        self.rows=[];self.day_rows={};self.rendered_month=None;self.visible_event_limit=30
        root=QVBoxLayout(self);root.setContentsMargins(0,0,0,0);root.setSpacing(0)
        body=QWidget();self.body_layout=QVBoxLayout(body);self.body_layout.setContentsMargins(0,0,4,0);self.body_layout.setSpacing(14)
        self.hero=CalendarHero();self.hero.illustration_requested.connect(self.preview_illustration);self.body_layout.addWidget(self.hero)
        self.history=AlertHistory(pet,'event',self.open_alert);self.body_layout.addWidget(self.history)
        self.middle=QWidget();self.middle_layout=QBoxLayout(QBoxLayout.Direction.LeftToRight,self.middle)
        self.middle_layout.setContentsMargins(0,0,0,0);self.middle_layout.setSpacing(18)
        self.month_box=CalendarBackdrop(self.hero);month_layout=QVBoxLayout(self.month_box);month_layout.setContentsMargins(12,12,12,12);month_layout.setSpacing(8)
        self.month_button=self.hero.month_button;self.month_button.clicked.connect(self.jump_month)
        tools=self.hero.tools
        self.today_button=button('Oggi',self.today,tools,role='quiet')
        icon_button('left','Mese precedente',lambda:self.change_month(-1),tools);icon_button('right','Mese successivo',lambda:self.change_month(1),tools)
        tools.addStretch()
        self.grid=QGridLayout();self.grid.setContentsMargins(0,0,0,0);self.grid.setSpacing(3)
        for col,label in enumerate(SHORT_DAYS):
            lab=plain_label(label,'muted');lab.setAlignment(Qt.AlignmentFlag.AlignCenter);lab.setStyleSheet('font-size:11px;color:#d0c8dc;');self.grid.addWidget(lab,0,col)
        for row in range(1,7):self.grid.setRowMinimumHeight(row,39)
        self.days=[]
        for i in range(42):
            b=DayButton(self.selected);b.clicked.connect(lambda checked=False,index=i:self.select_day(self.days[index].day,focus=True))
            b.moved.connect(lambda delta,index=i:self.select_day(self.days[index].day+timedelta(days=delta),focus=True))
            b.month_moved.connect(self.change_month);b.today_requested.connect(self.today)
            b.activated.connect(lambda index=i:self.new_event(self.days[index].day));self.days.append(b);self.grid.addWidget(b,i//7+1,i%7)
        month_layout.addLayout(self.grid);self.middle_layout.addWidget(self.month_box,3)
        self.agenda_box=QWidget();self.agenda_box.setMinimumWidth(180);agenda=QVBoxLayout(self.agenda_box);agenda.setContentsMargins(0,5,0,0);agenda.setSpacing(10)
        heading=QHBoxLayout();heading.setSpacing(4);self.day_title=plain_label('','section');heading.addWidget(self.day_title,1)
        self.new_button=icon_button('plus','Nuovo impegno',lambda:self.new_event(),heading);agenda.addLayout(heading)
        self.events_widget=QWidget();self.events_layout=QVBoxLayout(self.events_widget);self.events_layout.setContentsMargins(0,0,0,0);self.events_layout.setSpacing(8)
        agenda.addWidget(self.events_widget);agenda.addStretch();self.middle_layout.addWidget(self.agenda_box,2)
        self.body_layout.addWidget(self.middle);self.body_layout.addStretch();root.addWidget(scroll_page(body))
        signal=getattr(pet,'agenda_changed',None)
        if signal is not None and hasattr(signal,'connect'):signal.connect(self.refresh_if_visible)
        self.refresh()
    def showEvent(self,event):super().showEvent(event);self.refresh()
    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.middle_layout.setDirection(QBoxLayout.Direction.LeftToRight if self.width()>=680 else QBoxLayout.Direction.TopToBottom)
        self.hero.setFixedHeight(180 if self.width()>=680 else 145)
    def refresh_if_visible(self,*_):
        if self.isVisible():self.refresh()
    def refresh(self):
        self.history.refresh()
        first=self.month-timedelta(days=self.month.weekday());end=first+timedelta(days=42)
        self.rows=self.store.occurrences(first.isoformat(),end.isoformat())
        self.day_rows={}
        for row in self.rows:
            start=parse_local(row['start_local']).date();finish=parse_local(row.get('end_local') or row['start_local'])
            last=finish.date()
            # Midnight is an exclusive boundary for both all-day and timed events.
            if finish.time()==time() and last>start:last-=timedelta(days=1)
            cur=max(first,start);last=min(end-timedelta(days=1),last)
            while cur<=last:self.day_rows.setdefault(cur,[]).append(row);cur+=timedelta(days=1)
        for day,rows in self.day_rows.items():rows.sort(key=lambda r:(not r.get('all_day'),r['start_local'],r['title']))
        self.month_button.setText(f'{MONTHS[self.month.month-1]}\n{self.month.year}')
        if self.rendered_month!=self.month:
            self.hero.set_month(self.month);self.month_box.update();self.rendered_month=self.month
        for i,b in enumerate(self.days):
            day=first+timedelta(days=i);b.update_day(day,day.month==self.month.month,day==self.selected,self.day_rows.get(day,[]))
        self.refresh_day()
    def refresh_day(self):
        self.day_title.setText(('Oggi · ' if self.selected==date.today() else '')+local_day_label(self.selected))
        while self.events_layout.count():
            item=self.events_layout.takeAt(0)
            if item.widget():item.widget().hide();item.widget().deleteLater()
        rows=self.day_rows.get(self.selected,[])
        if not rows:
            empty=plain_label('Nessun impegno','muted');empty.setContentsMargins(0,12,0,8);self.events_layout.addWidget(empty)
            self.events_layout.addWidget(button('Aggiungi',lambda:self.new_event(),glyph='plus',role='quiet'))
        for row in rows[:self.visible_event_limit]:
            tile=QFrame();tile.setObjectName('card');tile.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Fixed);layout=QVBoxLayout(tile);layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize);layout.setContentsMargins(12,10,12,10);layout.setSpacing(5)
            start=parse_local(row['start_local']);end=parse_local(row.get('end_local') or row['start_local'])
            stamp='Tutto il giorno' if row.get('all_day') else (f'{start:%H:%M}–{end:%H:%M}' if start.date()==end.date() else f'{start:%d/%m %H:%M} – {end:%d/%m %H:%M}')
            label=plain_label(stamp,'muted');label.setStyleSheet('font-size:11px;');layout.addWidget(label)
            title=button(row['title'].replace('&','&&'),lambda checked=False,r=row:self.edit_event(r),role='quiet')
            title.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed);title.setMinimumWidth(0)
            title.setStyleSheet('QPushButton {text-align:left;padding:2px 0;border:none;font-weight:600;}');title.setToolTip(row['title']);title.setAccessibleName('Modifica '+row['title']);layout.addWidget(title)
            if row.get('details'):
                details=plain_label(row['details'],'muted');details.setMaximumHeight(42);details.setToolTip(row['details']);layout.addWidget(details)
            lower=QHBoxLayout();lower.setSpacing(4)
            if row.get('recurrence'):lower.addWidget(plain_label(recurrence_label(row['recurrence']),'muted'),1)
            else:lower.addStretch()
            trash=icon_button('trash','Elimina impegno',lambda checked=False,r=row:self.delete_event(r),lower);trash.setFixedSize(26,26)
            layout.addLayout(lower);self.events_layout.addWidget(tile)
        if len(rows)>self.visible_event_limit:
            self.events_layout.addWidget(button(f'Mostra altri ({len(rows)-self.visible_event_limit})',self.more_events,role='quiet'))
    def more_events(self):
        self.visible_event_limit+=30;self.refresh_day()
    def select_day(self,day,focus=False):
        if not date(1900,1,1)<=day<date(9999,1,1):return
        if day!=self.selected:self.visible_event_limit=30
        self.selected=day
        if day.replace(day=1)!=self.month:self.month=day.replace(day=1);self.refresh()
        else:
            for b in self.days:
                b.chosen=b.day==day;b.setFocusPolicy(Qt.FocusPolicy.StrongFocus if b.chosen else Qt.FocusPolicy.NoFocus);b.update()
            self.refresh_day()
        if focus:
            for b in self.days:
                if b.day==day:b.setFocus();break
    def change_month(self,step):
        current=QDate(self.month.year,self.month.month,1).addMonths(step)
        if not current.isValid() or not 1900<=current.year()<=9998:return
        self.month=current.toPyDate();self.selected=self.month;self.visible_event_limit=30;self.refresh()
        for b in self.days:
            if b.day==self.selected:b.setFocus();break
    def today(self):self.select_day(date.today(),focus=True)
    def preview_illustration(self,path):
        dialog=IllustrationDialog(self.pet,self,path,self.month)
        try:
            if not dialog.canvas.pixmap.isNull():exec_dialog(dialog,self.pet)
        finally:dialog.deleteLater()
    def jump_month(self):
        dialog=MonthJumpDialog(self.pet,self,self.month)
        try:
            if exec_dialog(dialog,self.pet)==QDialog.DialogCode.Accepted:self.select_day(dialog.value())
        finally:dialog.deleteLater()
    def new_event(self,day=None):
        day=day or self.selected;dialog=EventDialog(self.pet,self,day=day)
        if exec_editor(dialog,self.pet)==QDialog.DialogCode.Accepted:self.refresh()
    def open_alert(self,row):
        day=parse_local(row['start_local']).date();self.select_day(day,focus=True)

    def scope(self,deleting=False):
        dialog=ScopeDialog(self.pet,self,deleting)
        try:
            return dialog.scope if exec_dialog(dialog,self.pet)==QDialog.DialogCode.Accepted else None
        finally:dialog.deleteLater()
    def edit_event(self,row):
        event=self.store.get(row['item_id']);scope=self.scope() if event.get('recurrence') else 'series'
        if scope is None:return
        dialog=EventDialog(self.pet,self,event=event,occurrence=row,scope=scope)
        if exec_editor(dialog,self.pet)==QDialog.DialogCode.Accepted:self.refresh()
    def delete_event(self,row):
        event=self.store.get(row['item_id'])
        if event.get('recurrence'):scope=self.scope(True)
        else:scope='series' if Messages.question(self,'Elimina impegno',f'Eliminare «{row["title"]}»?')==QMessageBox.StandardButton.Yes else None
        if scope is None:return
        self.store.delete(row['item_id'],row['occurrence_key'] if scope=='occurrence' else None);notify_changed(self.pet);self.refresh()
