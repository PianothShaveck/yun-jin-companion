# SPDX-License-Identifier: GPL-3.0-or-later
"""On-demand city search; no requests or active timers while settings are idle."""
import json
import sys
from pathlib import Path
from PyQt6.QtCore import Qt,QProcess,QTimer
from PyQt6.QtWidgets import (QWidget,QDialog,QHBoxLayout,QVBoxLayout,QSizePolicy,
    QLineEdit,QListWidget,QListWidgetItem,QDialogButtonBox)
from yun_jin_core import BASE
from yun_jin_dialogs import exec_dialog,owner_window
from yun_jin_ui import STYLE,button,plain_label
from yun_jin_weather import selected_location,location_label,MAX_RESPONSE


class CityDialog(QDialog):
    def __init__(self,pet,parent):
        super().__init__(owner_window(parent))
        self.pet=pet;self.selection=None;self.process=None;self.closed=False
        self.setWindowTitle('Città per il meteo');self.setWindowIcon(pet.windowIcon())
        self.setStyleSheet(STYLE);self.resize(530,330)
        layout=QVBoxLayout(self);layout.setContentsMargins(20,20,20,18);layout.setSpacing(12)
        row=QHBoxLayout();row.setSpacing(12)
        self.query=QLineEdit();self.query.setMaxLength(100)
        self.query.setPlaceholderText('Cerca una città');self.query.setAccessibleName('Città')
        row.addWidget(self.query,1)
        self.search=button('Cerca',self.start_search,row);self.search.setAutoDefault(False)
        self.search.setEnabled(False);layout.addLayout(row)
        self.results=QListWidget();self.results.setAccessibleName('Città trovate')
        layout.addWidget(self.results,1)
        self.status=plain_label('','muted');self.status.setWordWrap(True);self.status.hide()
        layout.addWidget(self.status)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.use=buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.use.setText('Usa città');self.use.setProperty('role','primary')
        self.use.setEnabled(False);self.use.setAutoDefault(False)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Annulla')
        buttons.accepted.connect(self.accept_selection);buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.timeout=QTimer(self);self.timeout.setSingleShot(True);self.timeout.timeout.connect(self.timed_out)
        self.query.textChanged.connect(self.query_changed);self.query.returnPressed.connect(self.start_search)
        self.results.currentItemChanged.connect(lambda *_:self.use.setEnabled(self.results.currentItem() is not None))
        self.results.itemActivated.connect(lambda *_:self.accept_selection())
        self.query.setFocus()

    def message(self,text):
        self.status.setText(text);self.status.setVisible(bool(text))

    def query_changed(self,*_):
        self.cancel_request();self.results.clear();self.message('')
        self.search.setEnabled(len(self.query.text().strip())>=2)

    def start_search(self):
        name=' '.join(self.query.text().split())
        if self.closed or len(name)<2:return
        self.cancel_request();self.results.clear();self.message('Cerco…');self.search.setEnabled(False)
        # The context outlives the dialog, so a cancelled process can finish
        # asynchronously after the dialog has been destroyed.
        process=QProcess(self.pet.context);self.process=process
        executable=Path(sys.executable)
        if sys.platform=='win32' and executable.name.lower()=='pythonw.exe':
            candidate=executable.with_name('python.exe')
            if candidate.is_file():executable=candidate
        process.setProgram(str(executable));process.setArguments([str(BASE/'yun_jin_weather.py')])
        payload=json.dumps({'operation':'cities','name':name},ensure_ascii=False).encode('utf-8')
        def send():
            if process is self.process:process.write(payload);process.closeWriteChannel()
        process.started.connect(send)
        process.finished.connect(lambda code,_:self.received(process,code))
        process.errorOccurred.connect(lambda error:self.received(process,-1)
                                      if error==QProcess.ProcessError.FailedToStart else None)
        # start() can emit FailedToStart before returning on Windows.
        self.timeout.start(7000);process.start()

    def received(self,process,code):
        if process is not self.process or self.closed:
            process.deleteLater();return
        self.process=None;self.timeout.stop()
        raw=bytes(process.readAllStandardOutput());process.deleteLater()
        self.search.setEnabled(len(self.query.text().strip())>=2)
        try:
            if code!=0 or len(raw)>MAX_RESPONSE:raise ValueError('Invalid response')
            data=json.loads(raw)
            if not isinstance(data,dict) or not isinstance(data.get('cities'),list):raise ValueError('No results')
            for row in data['cities'][:10]:
                city=selected_location(row)
                if city:
                    item=QListWidgetItem(location_label(city));item.setData(Qt.ItemDataRole.UserRole,city)
                    item.setToolTip(item.text());self.results.addItem(item)
            self.message('' if self.results.count() else 'Nessuna città trovata.')
        except (ValueError,TypeError):
            self.message('Ricerca non disponibile. Riprova.')

    def timed_out(self):
        self.cancel_request();self.search.setEnabled(len(self.query.text().strip())>=2)
        self.message('Ricerca non disponibile. Riprova.')

    def cancel_request(self):
        self.timeout.stop();process,self.process=self.process,None
        if process is not None:process.kill()

    def accept_selection(self):
        item=self.results.currentItem()
        if item is None:return
        self.selection=selected_location(item.data(Qt.ItemDataRole.UserRole))
        if self.selection is not None:self.accept()

    def done(self,result):
        self.closed=True;self.cancel_request();super().done(result)


class WeatherLocationRow(QWidget):
    def __init__(self,pet,parent=None):
        super().__init__(parent);self.pet=pet
        row=QHBoxLayout(self);row.setContentsMargins(0,0,0,0);row.setSpacing(12)
        label=plain_label('Città');row.addWidget(label)
        self.choice=button('',self.choose,row);self.choice.setAccessibleName('Scegli città per il meteo')
        self.choice.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        row.setStretch(1,1);label.setBuddy(self.choice)
        pet.context.location_changed.connect(self.refresh);self.refresh()

    def refresh(self):
        location=self.pet.context.weather_location
        self.choice.setText(location['city']+'…' if location else 'Scegli città…')
        self.choice.setToolTip(location_label(location) if location else 'Scegli una città per attivare il meteo.')

    def choose(self):
        dialog=CityDialog(self.pet,self)
        try:
            if exec_dialog(dialog,self.pet)==QDialog.DialogCode.Accepted:
                self.pet.context.set_weather_location(dialog.selection)
        finally:dialog.deleteLater()
        self.refresh()
