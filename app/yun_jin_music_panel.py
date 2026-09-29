# SPDX-License-Identifier: GPL-3.0-or-later
"""Metronome and stopwatch: one page per tool, only relevant controls."""
import csv
import time
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QTabWidget,
    QSpinBox,QCheckBox,QComboBox,QSlider,QTreeWidget,QTreeWidgetItem,QHeaderView,
    QFileDialog,QApplication,QMessageBox)
from yun_jin_ui import plain_label,button,stepper,card,scroll_page,BeatIndicator,icon_button
from yun_jin_dialogs import Messages, choose_files
from yun_jin_music import MetroConfig,format_elapsed


class MusicPanel(QWidget):
    def __init__(self,pet):
        super().__init__(); self.pet=pet; self.metro=pet.metronome; self.watch=pet.stopwatch
        outer=QVBoxLayout(self); outer.setContentsMargins(0,0,0,0)
        self.tabs=QTabWidget(); self.tabs.tabBar().hide(); outer.addWidget(self.tabs)
        self.build_metronome(); self.build_stopwatch()

    def build_metronome(self):
        page=QWidget(); layout=QVBoxLayout(page); layout.setContentsMargins(0,0,4,0); layout.setSpacing(14)
        config=self.metro.settings(); self.controls=[]
        def spin(low,high,value):
            s=QSpinBox(); s.setRange(low,high); s.setValue(value); self.controls.append(s); return s
        hero,display=card(layout,hero=True)
        self.bpm=spin(20,400,config.bpm); self.bpm.setObjectName('tempo'); self.bpm.setSuffix(' BPM')
        self.bpm.setAccessibleName('Tempo in BPM'); self.bpm.setMinimumWidth(240)
        self.bpm_controls=stepper(self.bpm)
        row=QHBoxLayout(); row.setSpacing(12); row.addStretch(); row.addWidget(self.bpm_controls); row.addStretch(); display.addLayout(row)
        self.beat_display=plain_label('', 'metric'); self.beat_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        display.addWidget(self.beat_display)
        self.beats=BeatIndicator(); self.beats.set_beat(-1,config.accent); display.addWidget(self.beats)
        self.beat_count=plain_label('', 'muted'); self.beat_count.setAlignment(Qt.AlignmentFlag.AlignCenter); display.addWidget(self.beat_count)
        row=QHBoxLayout(); row.setSpacing(12); row.addStretch()
        self.start=button('Avvia',self.start_metro,row,glyph='play',role='primary')
        self.stop=button('Ferma',lambda:self.metro.stop(),row,glyph='stop',role='primary')
        self.tap=button('Tap tempo',self.tap_tempo,row); self.tap_times=[]; row.addStretch(); display.addLayout(row)
        self.configuration,parameters=card(layout)
        row=QHBoxLayout(); row.setSpacing(12)
        self.accent_on=QCheckBox('Accento'); self.accent_on.setChecked(config.accent>0); self.controls.append(self.accent_on)
        row.addWidget(self.accent_on)
        self.accent=spin(1,32,config.accent or 4); self.accent.setSuffix(' battiti'); self.accent.setAccessibleName('Battiti per accento')
        self.accent_box=stepper(self.accent); row.addWidget(self.accent_box,1); parameters.addLayout(row)
        self.accent_on.toggled.connect(lambda v:self.accent_box.setVisible(v))
        self.accent_on.toggled.connect(self.preview_beats); self.accent.valueChanged.connect(self.preview_beats)
        self.ramp=QCheckBox('Scalata'); self.ramp.setChecked(config.ramp); self.controls.append(self.ramp); parameters.addWidget(self.ramp)
        self.target=spin(20,400,config.target); self.target.setSuffix(' BPM')
        self.step=spin(1,100,config.step); self.step.setSuffix(' BPM'); self.every=spin(1,3600,config.every)
        self.unit=QComboBox(); self.unit.addItem('battiti','beats'); self.unit.addItem('secondi','seconds')
        self.unit.setCurrentIndex(max(0,self.unit.findData(config.unit))); self.controls.append(self.unit)
        self.finish=QComboBox(); self.finish.addItem('Continua','hold'); self.finish.addItem('Ferma dopo l’ultimo intervallo','stop')
        self.finish.setCurrentIndex(max(0,self.finish.findData(config.finish))); self.controls.append(self.finish)
        self.ramp_box=QWidget(); rf=QFormLayout(self.ramp_box); rf.setContentsMargins(0,0,0,0); rf.setVerticalSpacing(10)
        rf.addRow('Arrivo',stepper(self.target)); rf.addRow('Passo',stepper(self.step))
        row=QHBoxLayout(); row.setSpacing(12); row.addWidget(stepper(self.every),1); row.addWidget(self.unit); rf.addRow('Ogni',row)
        rf.addRow('Al termine',self.finish); parameters.addWidget(self.ramp_box)
        self.ramp.toggled.connect(self.ramp_box.setVisible); self.ramp_box.setVisible(config.ramp)
        vol=QHBoxLayout(); vol.setSpacing(12); vol.addWidget(plain_label('Volume'))
        self.volume=QSlider(Qt.Orientation.Horizontal); self.volume.setRange(0,100); self.volume.setValue(self.metro.volume)
        self.volume.setAccessibleName('Volume metronomo'); self.volume.valueChanged.connect(self.metro.set_volume)
        self.volume_label=plain_label(f'{self.metro.volume}%'); self.volume_label.setMinimumWidth(38)
        self.volume.valueChanged.connect(lambda v:self.volume_label.setText(f'{v}%'))
        vol.addWidget(self.volume,1); vol.addWidget(self.volume_label); layout.addLayout(vol)
        self.status=plain_label('', 'alert'); layout.addWidget(self.status); layout.addStretch()
        self.tabs.addTab(scroll_page(page),'Metronomo')
        self.metro.changed.connect(self.refresh_metro); self.metro.beat.connect(self.show_beat); self.refresh_metro()

    def build_stopwatch(self):
        page=QWidget(); layout=QVBoxLayout(page); layout.setContentsMargins(0,0,0,0); layout.setSpacing(14)
        hero,display=card(layout,hero=True)
        self.clock=plain_label('', 'metric'); self.clock.setAlignment(Qt.AlignmentFlag.AlignCenter); display.addWidget(self.clock)
        row=QHBoxLayout(); row.setSpacing(12); row.addStretch()
        self.watch_start=button('Avvia',self.start_watch,row,glyph='play',role='primary')
        self.watch_pause=button('Pausa',self.watch.pause,row,glyph='pause',role='primary')
        self.watch_lap=button('Parziale',self.lap_watch,row,glyph='plus')
        self.watch_reset=icon_button('reset','Azzera',self.watch.reset,row); row.addStretch(); display.addLayout(row)
        self.laps=QTreeWidget(); self.laps.setRootIsDecorated(False); self.laps.setHeaderLabels(['#','Parziale','Totale'])
        self.laps.header().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        for column in (1,2):self.laps.header().setSectionResizeMode(column,QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.laps,1)
        row=QHBoxLayout(); row.setSpacing(12); row.addStretch()
        self.copy=button('Copia',self.copy_laps,row,glyph='copy'); self.export=button('CSV…',self.export_laps,row,glyph='export')
        layout.addLayout(row); self.tabs.addTab(page,'Cronometro')
        self.watch.changed.connect(self.refresh_watch); self.refresh_watch()
        self.clock_timer=QTimer(self); self.clock_timer.setInterval(50); self.clock_timer.timeout.connect(self.refresh_clock); self.clock_timer.start()

    def start_metro(self):
        c=MetroConfig(self.bpm.value(),self.accent.value() if self.accent_on.isChecked() else 0,
            self.ramp.isChecked(),self.target.value(),self.step.value(),self.every.value(),self.unit.currentData(),self.finish.currentData())
        self.pet.speech.stop(announce=False); self.metro.start(c)

    def preview_beats(self,*_):
        if not self.metro.running:self.beats.set_beat(-1,self.accent.value() if self.accent_on.isChecked() else 0)

    def refresh_metro(self):
        running=self.metro.running; self.configuration.setEnabled(not running)
        self.accent_box.setVisible(self.accent_on.isChecked()); self.accent_box.setEnabled(not running)
        self.start.setEnabled(not running); self.start.setVisible(not running)
        self.stop.setEnabled(running); self.stop.setVisible(running); self.tap.setVisible(not running)
        self.bpm_controls.setVisible(not running); self.beat_display.setVisible(running)
        if running:self.beat_display.setText(f'{self.metro.bpm} BPM')
        self.status.setText(self.metro.status)
        self.status.setVisible(self.metro.status not in ('Pronto.','In esecuzione','Fermo.',''))
        if not running:self.beat_count.hide(); self.preview_beats()

    def show_beat(self,index,bpm,accented):
        group=self.metro.stream.plan.config.accent; position=index%group if group else index
        self.beat_display.setText(f'{bpm} BPM'); self.beats.set_beat(position,group)
        self.beats.setAccessibleDescription(f'Battito {position+1}' + (f' di {group}' if group else ''))
        self.beat_count.setText(f'{position+1} / {group}' if group else str(index+1))
        self.beat_count.setVisible(group>12 or not group)

    def tap_tempo(self):
        now=time.monotonic()
        if self.tap_times and now-self.tap_times[-1]>4:self.tap_times=[]
        self.tap_times=(self.tap_times+[now])[-6:]
        if len(self.tap_times)>1:
            elapsed=self.tap_times[-1]-self.tap_times[0]
            if elapsed>0:self.bpm.setValue(round(60*(len(self.tap_times)-1)/elapsed))

    def start_watch(self):
        self.watch.start(); self.pet.queue_feedback('chronometer','review')

    def lap_watch(self):
        if self.watch.lap() is not None:self.pet.queue_feedback('chronometer','wave')

    def refresh_clock(self):self.clock.setText(format_elapsed(self.watch.elapsed()))

    def refresh_watch(self):
        self.refresh_clock(); self.watch_start.setVisible(not self.watch.running); self.watch_pause.setVisible(self.watch.running)
        self.watch_start.setText('Riprendi' if self.watch.elapsed()>0 else 'Avvia')
        self.watch_lap.setEnabled(self.watch.running); self.watch_reset.setEnabled(self.watch.running or self.watch.elapsed()>0 or bool(self.watch.laps))
        self.copy.setEnabled(bool(self.watch.laps)); self.export.setEnabled(bool(self.watch.laps))
        self.laps.clear()
        for i,lap in enumerate(self.watch.laps,1):
            self.laps.addTopLevelItem(QTreeWidgetItem([f'{i:02d}',format_elapsed(lap['split']),format_elapsed(lap['total'])]))

    def copy_laps(self):
        rows=['Parziale\tDurata\tTotale']
        rows += [f'{i:02d}\t{format_elapsed(lap["split"])}\t{format_elapsed(lap["total"])}' for i,lap in enumerate(self.watch.laps,1)]
        QApplication.clipboard().setText('\n'.join(rows))

    def export_laps(self):
        files=choose_files(self,'Esporta parziali',mode='save',
            filename='parziali-yun-jin.csv',name_filter='CSV (*.csv)')
        path=files[0] if files else ''
        if not path:return
        try:
            with open(path,'w',encoding='utf-8-sig',newline='') as f:
                writer=csv.writer(f); writer.writerow(['Parziale','Durata secondi','Totale secondi'])
                for i,lap in enumerate(self.watch.laps,1):writer.writerow([i,round(lap['split'],3),round(lap['total'],3)])
        except OSError as exc:Messages.warning(self,'Esportazione non riuscita',str(exc))
