# SPDX-License-Identifier: GPL-3.0-or-later
"""Companion tools with compact navigation and contextual controls."""
import time
import sys
from pathlib import Path
from datetime import datetime
from PyQt6.QtCore import Qt, QDateTime, QTimer, QUrl, QSize
from PyQt6.QtGui import QPixmap, QImageReader
from PyQt6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QTextEdit, QTabWidget, QWidget, QListWidget,
    QListWidgetItem, QSplitter, QTreeWidget, QTreeWidgetItem, QSpinBox, QComboBox,
    QDateTimeEdit, QDialogButtonBox, QFileDialog, QMessageBox, QCheckBox, QSlider,
    QMenu, QHeaderView)
from yun_jin_platform import shortcut_help
from yun_jin_dialogs import Messages, choose_files, owner_window, exec_dialog
from yun_jin_ui import (STYLE, button, plain_label, stepper, icon, icon_button,
    menu_button, card, scroll_page, FeedbackLabel)


class ReminderDialog(QDialog):
    def __init__(self, pet, existing=None):
        super().__init__(owner_window(pet))
        self.pet, self.existing = pet, existing
        self.setWindowTitle('Modifica promemoria' if existing else 'Nuovo promemoria')
        self.setWindowIcon(pet.windowIcon()); self.setStyleSheet(STYLE)
        self.setMinimumWidth(420)
        layout=QVBoxLayout(self); layout.setContentsMargins(22,22,22,18); layout.setSpacing(16)
        self.title=QLineEdit(existing['title'] if existing else '')
        self.title.setPlaceholderText('Cosa vuoi ricordare?')
        self.title.setAccessibleName('Promemoria'); layout.addWidget(self.title)
        self.kind=QComboBox(); self.kind.addItems(['Tra', 'Data e ora'])
        self.kind.setAccessibleName('Quando')
        self.minutes=QSpinBox(); self.minutes.setRange(1,60*24*30)
        self.minutes.setValue(20); self.minutes.setSuffix(' min'); self.minutes.setAccessibleName('Minuti')
        self.duration_controls=stepper(self.minutes)
        self.when=QDateTimeEdit(); self.when.setCalendarPopup(True)
        self.when.setDisplayFormat('dd/MM/yyyy HH:mm')
        self.when.setDateTime(QDateTime.fromSecsSinceEpoch(int(existing['due'])) if existing else QDateTime.currentDateTime().addSecs(1200))
        row=QHBoxLayout(); row.setSpacing(12); row.addWidget(self.kind); row.addWidget(self.duration_controls,1); row.addWidget(self.when,1)
        layout.addLayout(row)
        self.quick_choices=QWidget(); quick=QHBoxLayout(self.quick_choices); quick.setSpacing(12); quick.setContentsMargins(0,0,0,0)
        for minute in (5,15,25,60):
            button(f'{minute} min',lambda checked=False,m=minute:self.quick(m),quick,role='quiet')
        layout.addWidget(self.quick_choices)
        self.kind.currentIndexChanged.connect(self.update_kind)
        self.kind.setCurrentIndex(1 if existing else 0); self.update_kind()
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        save=buttons.button(QDialogButtonBox.StandardButton.Save); save.setText('Salva'); save.setProperty('role','primary')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Annulla')
        buttons.accepted.connect(self.submit); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons); self.title.setFocus()

    def quick(self,minutes):
        self.kind.setCurrentIndex(0); self.minutes.setValue(minutes)

    def update_kind(self):
        relative=self.kind.currentIndex()==0
        self.duration_controls.setVisible(relative); self.quick_choices.setVisible(relative)
        self.when.setVisible(not relative)
        QTimer.singleShot(0,self.adjustSize)

    def submit(self):
        due=time.time()+self.minutes.value()*60 if self.kind.currentIndex()==0 else self.when.dateTime().toSecsSinceEpoch()
        if not self.title.text().strip():
            self.title.setFocus(); return
        if due<=time.time():
            Messages.information(self,'Data passata','Scegli una data futura.'); return
        self.pet.store.add_reminder(self.title.text(),due,self.existing['id'] if self.existing else None)
        self.pet.sound.play('saved'); self.pet.refresh_reminders(); self.accept()


class Panel(QDialog):
    def __init__(self,pet):
        super().__init__(None)
        self.pet=pet; self.setWindowTitle('Yun Jin'); self.setWindowIcon(pet.windowIcon())
        self.setStyleSheet(STYLE); self.resize(990,690); self.setMinimumSize(760,550)
        self.setAcceptDrops(True)
        self.note_id=None; self.note_path=''; self.loading=False; self.dirty=False; self.reminder_signature=None
        layout=QHBoxLayout(self); layout.setSpacing(12); layout.setContentsMargins(12,12,18,12); layout.setSpacing(18)
        sidebar=QWidget(); sidebar.setObjectName('sidebar'); sidebar.setFixedWidth(182)
        side=QVBoxLayout(sidebar); side.setContentsMargins(10,16,10,12); side.setSpacing(5)
        brand=QHBoxLayout(); brand.setSpacing(12); brand.setSpacing(8)
        portrait=QLabel(); portrait.setPixmap(pet.windowIcon().pixmap(38,38)); portrait.setFixedSize(38,38)
        brand.addWidget(portrait); brand.addWidget(plain_label('Yun Jin','brand')); brand.addStretch()
        side.addLayout(brand); side.addSpacing(20)
        self.nav={}
        for label,glyph,page,sub in [('Appunti','note',0,None),('Promemoria','bell',1,None),
                ('Studio','cards',6,None),('Focus','focus',4,None),('Metronomo','metro',5,0),('Cronometro','clock',5,1)]:
            self.add_navigation(side,label,glyph,page,sub)
        side.addStretch()
        self.add_navigation(side,'Voce','voice',3,None)
        self.add_navigation(side,'Impostazioni','settings',2,None)
        button('Guida',self.pet.open_guide,side,glyph='help',role='nav')
        layout.addWidget(sidebar)
        content=QVBoxLayout(); content.setContentsMargins(0,6,0,0); content.setSpacing(8); layout.addLayout(content,1)
        # Stable indices keep hotkeys, tray actions and stored workflows compatible.
        self.tabs=QTabWidget(); self.tabs.tabBar().hide(); content.addWidget(self.tabs,1)
        self.status=FeedbackLabel()
        self.build_notes(); self.build_reminders(); self.build_settings(); self.build_voice(); self.build_focus()
        from yun_jin_music_panel import MusicPanel
        self.music=MusicPanel(pet); self.tabs.addTab(self.music,'Musica')
        from yun_jin_study_ui import StudyPanel
        self.study=StudyPanel(pet);self.tabs.addTab(self.study,'Studio')
        self.music.tabs.currentChanged.connect(self.sync_navigation)
        self.tabs.currentChanged.connect(self.sync_navigation)
        content.addWidget(self.status)
        self.autosave=QTimer(self); self.autosave.setSingleShot(True); self.autosave.timeout.connect(self.autosave_note)
        self.title.textEdited.connect(self.changed); self.body.textChanged.connect(self.changed)
        self.refresh_notes(); self.refresh_reminders(); self.sync_navigation()

    def add_navigation(self,layout,label,glyph,page,sub):
        b=button(label,lambda checked=False,p=page,s=sub:self.show_page(p,s),layout,glyph=glyph,role='nav')
        b.setIconSize(QSize(20,20)); b.setCheckable(True); self.nav[(page,sub)]=b

    def show_page(self,page,sub=None):
        if page==5 and sub is not None:self.music.tabs.setCurrentIndex(sub)
        self.tabs.setCurrentIndex(page); self.sync_navigation()

    def sync_navigation(self,*_):
        page=self.tabs.currentIndex(); sub=self.music.tabs.currentIndex() if page==5 else None
        for key,b in self.nav.items():b.setChecked(key==(page,sub))

    def build_notes(self):
        tab=QWidget(); main=QVBoxLayout(tab); main.setContentsMargins(0,0,0,0); main.setSpacing(12)
        tools=QHBoxLayout(); tools.setSpacing(12)
        button('Nuovo',self.new_note,tools,glyph='plus',role='primary')
        imports=QMenu(self); imports.addAction(icon('copy'),'Appunti copiati',self.pet.capture_clipboard)
        imports.addAction(icon('file'),'File…',self.add_file); imports.addAction(icon('folder'),'Cartella…',self.add_folder)
        menu_button('Importa',imports,tools,glyph='folder'); tools.addStretch(); main.addLayout(tools)
        split=QSplitter(); split.setChildrenCollapsible(False); split.setHandleWidth(12)
        left=QWidget(); left.setMinimumWidth(160); l=QVBoxLayout(left); l.setContentsMargins(0,0,0,0); l.setSpacing(8)
        self.search=QLineEdit(); self.search.setPlaceholderText('Cerca'); self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName('Cerca appunti'); self.search.textChanged.connect(self.refresh_notes); l.addWidget(self.search)
        self.notes_list=QListWidget(); self.notes_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.notes_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.notes_list.currentItemChanged.connect(self.select_note); l.addWidget(self.notes_list)
        split.addWidget(left)
        right=QWidget(); right.setMinimumWidth(340); r=QVBoxLayout(right); r.setContentsMargins(0,0,0,0); r.setSpacing(8)
        self.title=QLineEdit(); self.title.setPlaceholderText('Titolo'); self.title.setAccessibleName('Titolo'); r.addWidget(self.title)
        self.body=QTextEdit(); self.body.setAcceptRichText(False); self.body.setPlaceholderText('Scrivi o trascina un file…')
        self.body.setAccessibleName('Testo'); r.addWidget(self.body,1)
        material=QHBoxLayout(); material.setSpacing(12); self.path_label=plain_label('', 'muted'); material.addWidget(self.path_label,1)
        self.open_file=button('Apri',self.open_material,material,glyph='file'); self.open_file.hide(); r.addLayout(material)
        self.preview=QLabel(); self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter); self.preview.setMaximumHeight(130)
        self.preview.hide(); r.addWidget(self.preview)
        actions=QHBoxLayout(); actions.setSpacing(12); button('Leggi',self.read_note,actions,glyph='voice')
        self.note_stop=icon_button('stop','Interrompi voce',self.pet.stop_speech,actions); self.note_stop.hide()
        self.pet.speech.status_changed.connect(lambda _:self.note_stop.setVisible(self.pet.speech.busy))
        self.pet.speech.active_changed.connect(lambda _:self.note_stop.setVisible(self.pet.speech.busy))
        ai_toggle=button('ChatGPT',None,actions,glyph='spark'); ai_toggle.setCheckable(True)
        actions.addStretch()
        more=QMenu(self); more.addAction('Salva',self.save_clicked); more.addSeparator(); more.addAction('Elimina',self.delete_note)
        overflow=menu_button('',more,actions); overflow.setAccessibleName('Azioni appunto'); overflow.setToolTip('Azioni appunto')
        r.addLayout(actions)
        self.ai_box=QWidget(); ai_layout=QVBoxLayout(self.ai_box); ai_layout.setContentsMargins(0,0,0,0); ai_layout.setSpacing(8)
        ai=QHBoxLayout(); ai.setSpacing(12); self.ai_mode=QComboBox(); self.ai_mode.addItems(['Spiega','Traduci','Rivedi','Domanda'])
        self.ai_mode.setAccessibleName('Richiesta ChatGPT'); ai.addWidget(self.ai_mode,1)
        button('Copia e apri',self.ask_ai,ai,glyph='copy'); ai_layout.addLayout(ai)
        self.question=QLineEdit(); self.question.setPlaceholderText('Istruzioni facoltative'); ai_layout.addWidget(self.question)
        self.ai_box.hide(); ai_toggle.toggled.connect(self.ai_box.setVisible); r.addWidget(self.ai_box)
        split.addWidget(right); split.setSizes([205,505]); main.addWidget(split)
        self.tabs.addTab(tab,'Appunti')

    def build_focus(self):
        tab=QWidget(); layout=QVBoxLayout(tab); layout.setContentsMargins(0,0,0,0); layout.setSpacing(16)
        layout.addStretch()
        hero,display=card(layout,hero=True)
        self.focus_status=plain_label('', 'metric'); self.focus_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        display.addWidget(self.focus_status)
        self.focus_minutes=QSpinBox(); self.focus_minutes.setRange(1,180)
        self.focus_minutes.setValue(int(self.pet.store.preference('focus_minutes',25))); self.focus_minutes.setSuffix(' min')
        self.focus_minutes.setObjectName('tempo'); self.focus_minutes.setMinimumWidth(190)
        self.focus_minutes.setAccessibleName('Durata focus'); self.focus_minutes.valueChanged.connect(self.refresh_focus)
        self.focus_duration_controls=stepper(self.focus_minutes)
        row=QHBoxLayout(); row.setSpacing(12); row.addStretch(); row.addWidget(self.focus_duration_controls); row.addStretch(); display.addLayout(row)
        row=QHBoxLayout(); row.setSpacing(12); row.addStretch()
        self.focus_start=button('Avvia',lambda:self.pet.start_focus(self.focus_minutes.value()),row,glyph='play',role='primary')
        self.focus_stop=button('Interrompi',self.pet.stop_focus,row,glyph='stop'); row.addStretch(); display.addLayout(row)
        layout.addStretch(2); self.tabs.addTab(tab,'Focus'); self.refresh_focus()

    def refresh_focus(self):
        row=self.pet.focus_row(); active=False
        if row and row['status']=='pending' and row['due']>time.time():
            import math
            seconds=max(0,math.ceil(row['due']-time.time())); active=True
            self.focus_status.setText(f'{seconds//60:02d}:{seconds%60:02d}')
        elif row:self.focus_status.setText('Pausa')
        else:self.focus_status.setText(f'{self.focus_minutes.value():02d}:00')
        self.focus_status.setVisible(active)
        self.focus_start.setVisible(not active); self.focus_stop.setVisible(active)
        self.focus_duration_controls.setVisible(not active)

    def build_reminders(self):
        tab=QWidget(); layout=QVBoxLayout(tab); layout.setContentsMargins(0,0,0,0); layout.setSpacing(12)
        top=QHBoxLayout(); top.setSpacing(12); button('Nuovo',self.pet.new_reminder,top,glyph='plus',role='primary'); top.addStretch()
        self.show_done=QCheckBox('Completati'); self.show_done.toggled.connect(lambda _:self.refresh_reminders(force=True))
        top.addWidget(self.show_done); layout.addLayout(top)
        self.reminders=QTreeWidget(); self.reminders.setRootIsDecorated(False)
        self.reminders.setHeaderLabels(['Promemoria','Scadenza','Stato'])
        self.reminders.header().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        for col in (1,2):self.reminders.header().setSectionResizeMode(col,QHeaderView.ResizeMode.ResizeToContents)
        self.reminders.itemDoubleClicked.connect(lambda *_:self.edit_reminder()); layout.addWidget(self.reminders)
        self.reminder_actions=QWidget(); actions=QHBoxLayout(self.reminder_actions); actions.setSpacing(12); actions.setContentsMargins(0,0,0,0)
        button('Fatto',self.complete_reminder,actions,glyph='check',role='primary')
        self.snooze_minutes=QSpinBox(); self.snooze_minutes.setRange(1,1440); self.snooze_minutes.setValue(10)
        self.snooze_minutes.setSuffix(' min'); self.snooze_minutes.setAccessibleName('Rimanda di')
        actions.addWidget(self.snooze_minutes); button('Rimanda',self.snooze_reminder,actions); actions.addStretch()
        more=QMenu(self); more.addAction('Modifica',self.edit_reminder); more.addAction('Elimina',self.delete_reminder)
        overflow=menu_button('',more,actions); overflow.setToolTip('Azioni promemoria'); overflow.setAccessibleName('Azioni promemoria')
        layout.addWidget(self.reminder_actions)
        self.reminders.itemSelectionChanged.connect(lambda:self.reminder_actions.setEnabled(self.selected_reminder() is not None))
        self.reminder_actions.setEnabled(False); self.tabs.addTab(tab,'Promemoria')

    def build_settings(self):
        tab=QWidget(); layout=QVBoxLayout(tab); layout.setContentsMargins(0,0,4,0); layout.setSpacing(16)
        _,sounds=card(layout)
        sounds.addWidget(plain_label('Suoni','section'))
        self.sound_enabled=QCheckBox('Effetti sonori')
        self.sound_enabled.setChecked(self.pet.sound.enabled)
        sounds.addWidget(self.sound_enabled)
        self.sound_enabled.setToolTip('Campanello e suoni del personaggio. Voce e metronomo hanno volumi separati.')
        self.sound_options=QWidget(); options=QVBoxLayout(self.sound_options)
        options.setContentsMargins(28,0,0,0); options.setSpacing(12)
        self.interaction_sounds=QCheckBox('Saluti e conferme')
        self.interaction_sounds.setChecked(self.pet.sound.interactions)
        self.interaction_sounds.setToolTip('Suoni di saluto, salvataggio e completamento.')
        self.interaction_sounds.toggled.connect(self.set_interactions)
        options.addWidget(self.interaction_sounds)
        row=QHBoxLayout(); row.setSpacing(12); row.addWidget(plain_label('Volume'))
        self.volume=QSlider(Qt.Orientation.Horizontal); self.volume.setRange(0,100); self.volume.setValue(round(self.pet.sound.volume*100))
        self.volume.setAccessibleName('Volume effetti'); self.volume.valueChanged.connect(self.set_volume); row.addWidget(self.volume,1)
        self.sound_volume_value=plain_label(f'{self.volume.value()}%'); self.sound_volume_value.setMinimumWidth(38)
        row.addWidget(self.sound_volume_value)
        self.volume.valueChanged.connect(lambda v:self.sound_volume_value.setText(f'{v}%'))
        icon_button('volume','Ascolta campanello',lambda:self.pet.sound.play('reminder',preview=True),row)
        options.addLayout(row); sounds.addWidget(self.sound_options)
        self.sound_options.setEnabled(self.sound_enabled.isChecked())
        self.sound_enabled.toggled.connect(self.set_sound)
        self.pet.sound.prepare()
        self.sound_status=plain_label(self.pet.sound.status,'alert'); sounds.addWidget(self.sound_status)
        self.sound_status.setVisible(bool(self.pet.sound.status))
        _,character=card(layout)
        character.addWidget(plain_label('Personaggio','section'))
        self.character_visible=QCheckBox('Mostra Yun Jin')
        self.sync_character_visibility()
        self.character_visible.toggled.connect(self.pet.set_character_visible)
        character.addWidget(self.character_visible)
        extras=QCheckBox('Animazioni aggiuntive'); extras.setChecked(self.pet.use_extra_animations)
        extras.toggled.connect(self.pet.set_extra_animations); character.addWidget(extras)
        if sys.platform=='darwin':
            from yun_jin_macos import LABEL
            self.mac_fullscreen=QCheckBox(LABEL)
            character.addWidget(self.mac_fullscreen)
            self.sync_mac_overlay()
            self.mac_fullscreen.toggled.connect(self.pet.set_mac_overlay)
        elif sys.platform=='win32':
            from yun_jin_windows_overlay import LABEL
            self.windows_fullscreen=QCheckBox(LABEL)
            character.addWidget(self.windows_fullscreen)
            self.sync_windows_overlay()
            self.windows_fullscreen.toggled.connect(self.pet.set_windows_overlay)
        _,context=card(layout)
        context.addWidget(plain_label('Orario e meteo','section'))
        self.context_checks={}
        for key, label, hint in (
                ('greeting', 'Saluto all’avvio', 'Una sola volta, secondo l’ora locale. Usa lingua, servizio e volume scelti in Voce.'),
                ('time', 'Animazioni secondo l’ora', 'Una reazione al cambio di fascia: mattina, pomeriggio, sera e notte.'),
                ('weather', 'Reazioni al meteo locale', 'Animazioni e brevi commenti nella lingua scelta in Voce. Meteo ogni ora da Open-Meteo; posizione approssimativa dall’indirizzo IP (ipwho.is).')):
            check=QCheckBox(label); check.setChecked(self.pet.context.enabled[key]); check.setToolTip(hint)
            check.toggled.connect(lambda value, key=key:self.pet.context.set_enabled(key,value))
            if key == 'weather':
                weather_row=QHBoxLayout(); weather_row.setSpacing(12)
                weather_row.addWidget(check); weather_row.addStretch(); context.addLayout(weather_row)
            else: context.addWidget(check)
            self.context_checks[key]=check
        credit=plain_label('<a href="https://open-meteo.com/" style="color:#b8b2c8">Open-Meteo</a>', 'muted')
        credit.setTextFormat(Qt.TextFormat.RichText); credit.setOpenExternalLinks(False)
        credit.linkActivated.connect(lambda url:self.pet.open_external(QUrl(url),self))
        credit.setToolTip('Dati meteo: Open-Meteo · CC BY 4.0. Posizione approssimativa: ipwho.is.')
        weather_row.addWidget(credit)
        _,updates=card(layout)
        updates.addWidget(plain_label('Aggiornamenti','section'))
        self.updates_enabled=QCheckBox('Aggiornamenti automatici')
        self.updates_enabled.setToolTip('Controlla ogni 2 ore. Puoi leggere le note prima di aggiornare, rimandare o saltare la versione.')
        self.updates_enabled.setChecked(self.pet.updates.enabled)
        self.updates_enabled.toggled.connect(self.pet.updates.set_enabled)
        updates.addWidget(self.updates_enabled)
        self.update_status=plain_label(self.pet.updates.status,'muted')
        self.update_status.setWordWrap(True); updates.addWidget(self.update_status)
        self.pet.updates.status_changed.connect(self.update_status.setText)
        row=QHBoxLayout(); row.setSpacing(12)
        self.update_check=button('Controlla ora',lambda:self.pet.updates.check(manual=True),row)
        self.update_notes=button('Note di rilascio…',self.pet.updates.show_notes,row)
        def sync_updates():
            self.update_check.setEnabled(not self.pet.updates.busy)
            self.update_notes.setEnabled(self.pet.updates.release is not None)
        self.pet.updates.available_changed.connect(sync_updates); sync_updates()
        row.addStretch(); updates.addLayout(row)
        _,data=card(layout)
        data.addWidget(plain_label('Dati e strumenti','section'))
        row=QHBoxLayout(); row.setSpacing(12); button('Backup…',self.backup,row,glyph='export')
        button('Cartella dati',lambda:self.pet.open_external(QUrl.fromLocalFile(str(self.pet.store.root)),self),row,glyph='folder')
        row.addStretch(); data.addLayout(row)
        row=QHBoxLayout(); row.setSpacing(12); button('Scorciatoie',self.show_shortcuts,row,glyph='help'); row.addStretch(); data.addLayout(row)
        self.hotkey_status=plain_label(self.pet.hotkey_status,'alert')
        self.hotkey_status.setVisible('Non disponibili' in self.pet.hotkey_status); layout.addWidget(self.hotkey_status)
        layout.addStretch(); self.tabs.addTab(scroll_page(tab),'Impostazioni')

    def show_shortcuts(self):
        from yun_jin_hotkeys import ShortcutDialog
        dialog=ShortcutDialog(self.pet,self)
        try: exec_dialog(dialog,self.pet)
        finally:
            dialog.deleteLater()
            self.hotkey_status.setText(self.pet.hotkey_status)
            self.hotkey_status.setVisible(bool(self.pet.hotkeys.errors))

    def sync_character_visibility(self):
        self.character_visible.blockSignals(True)
        self.character_visible.setChecked(not self.pet.character_hidden)
        self.character_visible.blockSignals(False)

    def sync_windows_overlay(self):
        if not hasattr(self,'windows_fullscreen'):return
        from yun_jin_windows_overlay import PREFERENCE
        self.windows_fullscreen.blockSignals(True)
        self.windows_fullscreen.setChecked(self.pet.store.preference(PREFERENCE,True))
        self.windows_fullscreen.blockSignals(False)

    def sync_mac_overlay(self):
        if not hasattr(self,'mac_fullscreen'):
            return
        controller=self.pet.mac_overlay
        self.mac_fullscreen.blockSignals(True)
        self.mac_fullscreen.setChecked(bool(controller and controller.enabled))
        self.mac_fullscreen.setEnabled(controller is not None)
        self.mac_fullscreen.blockSignals(False)
        text='L’icona nella barra dei menu resta disponibile anche con Yun Jin nascosta.'
        if controller is None or controller.error:
            text='Modalità overlay non disponibile. '+(controller.error if controller else 'Riavvia l’app e controlla il log nella cartella dati.')
        self.mac_fullscreen.setToolTip(text)

    def build_voice(self):
        tab=QWidget(); layout=QVBoxLayout(tab); layout.setContentsMargins(0,0,4,0); layout.setSpacing(14)
        voice=self.pet.speech
        self.tts_reminders=QCheckBox('Leggi i promemoria alla scadenza')
        self.tts_reminders.setChecked(voice.pref('auto_reminders',True))
        self.tts_reminders.toggled.connect(lambda v:voice.set_pref('auto_reminders',v))
        _,settings=card(layout)
        row=QHBoxLayout(); row.setSpacing(12); row.addWidget(plain_label('Voce','section')); row.addStretch()
        more=QMenu(self); more.addAction('Ripristina voce',self.reset_voice); more.addAction('Svuota cache',voice.clear_cache)
        overflow=menu_button('',more,row); overflow.setToolTip('Opzioni voce'); overflow.setAccessibleName('Opzioni voce')
        settings.addLayout(row)
        form=QFormLayout(); form.setVerticalSpacing(12); form.setHorizontalSpacing(18); self.voice_form=form
        self.provider=QComboBox(); self.provider.addItem('Microsoft Edge','edge'); self.provider.addItem('Google Translate','google')
        self.provider.setCurrentIndex(max(0,self.provider.findData(voice.pref('provider','edge')))); form.addRow('Servizio',self.provider)
        self.tts_language=QComboBox()
        for label,code in [('Italiano','it'),('Inglese','en'),('Mandarino','zh-CN')]:self.tts_language.addItem(label,code)
        self.tts_language.setCurrentIndex(max(0,self.tts_language.findData(voice.pref('language','it')))); form.addRow('Lingua',self.tts_language)
        self.tts_voice=QComboBox(); form.addRow('Voce',self.tts_voice)
        self.tts_rate=QSpinBox(); self.tts_rate.setRange(-40,40); self.tts_rate.setSuffix(' %')
        self.tts_rate.setValue(int(voice.pref('rate',20))); self.tts_rate.valueChanged.connect(lambda v:voice.set_pref('rate',v))
        self.rate_controls=stepper(self.tts_rate); form.addRow('Velocità',self.rate_controls)
        self.tts_pitch=QSpinBox(); self.tts_pitch.setRange(-15,15); self.tts_pitch.setSuffix(' Hz')
        self.tts_pitch.setValue(int(voice.pref('pitch',15))); self.tts_pitch.valueChanged.connect(lambda v:voice.set_pref('pitch',v))
        self.pitch_controls=stepper(self.tts_pitch); form.addRow('Intonazione',self.pitch_controls)
        self.google_slow=QCheckBox('Lettura lenta'); self.google_slow.setChecked(int(voice.pref('google_slow',0))==1)
        self.google_slow.toggled.connect(lambda v:voice.set_pref('google_slow',int(v))); form.addRow('',self.google_slow)
        self.tts_volume=QSlider(Qt.Orientation.Horizontal); self.tts_volume.setRange(0,100)
        self.tts_volume.setValue(int(voice.pref('volume',70))); self.tts_volume.setAccessibleName('Volume voce')
        self.tts_volume.valueChanged.connect(lambda v:voice.set_pref('volume',v))
        volume=QWidget(); vr=QHBoxLayout(volume); vr.setSpacing(12); vr.setContentsMargins(0,0,0,0); vr.addWidget(self.tts_volume,1)
        self.volume_label=plain_label(f'{self.tts_volume.value()}%'); self.volume_label.setMinimumWidth(38); vr.addWidget(self.volume_label)
        self.tts_volume.valueChanged.connect(lambda v:self.volume_label.setText(f'{v}%')); form.addRow('Volume',volume)
        settings.addLayout(form)
        settings.addWidget(self.tts_reminders)
        self.provider.setToolTip('Il testo viene inviato online al servizio scelto. Google sceglie la voce per la lingua.')
        _,reading=card(layout)
        self.tts_test=QLineEdit(); self.tts_test.setPlaceholderText('Testo da leggere'); self.tts_test.setAccessibleName('Testo da leggere')
        reading.addWidget(self.tts_test)
        row=QHBoxLayout(); row.setSpacing(12); button('Ascolta',lambda:voice.speak(self.tts_test.text(),preview=True),row,glyph='play',role='primary')
        button('Leggi testo copiato',self.pet.read_clipboard,row,glyph='copy'); row.addStretch()
        self.voice_stop=button('Stop',self.pet.stop_speech,row,glyph='stop'); reading.addLayout(row)
        self.voice_status=FeedbackLabel(); reading.addWidget(self.voice_status)
        def report(text):
            self.voice_status.setText(text); self.voice_stop.setVisible(voice.busy)
        voice.status_changed.connect(report)
        voice.active_changed.connect(lambda _:self.voice_stop.setVisible(voice.busy))
        report(voice.status)
        layout.addStretch()
        self.provider.currentIndexChanged.connect(self.voice_options); self.tts_language.currentIndexChanged.connect(self.voice_options)
        self.tts_voice.currentIndexChanged.connect(self.save_voice); self.voice_options()
        self.voice_scroll=scroll_page(tab); self.tabs.addTab(self.voice_scroll,'Voce')

    def voice_options(self):
        from yun_jin_speech import VOICES
        voice=self.pet.speech
        language=self.tts_language.currentData()
        provider=self.provider.currentData()
        voice.set_pref('provider',provider)
        voice.set_pref('language',language)
        selected=voice.pref('voice_'+language,VOICES[language][0][1])
        self.tts_voice.blockSignals(True)
        self.tts_voice.clear()
        for label,key in VOICES[language]:
            self.tts_voice.addItem(label.split(' · ')[0] + (' · UK' if key.startswith('en-GB') else ' · USA' if key.startswith('en-US') else ''),key)
        self.tts_voice.setCurrentIndex(max(0,self.tts_voice.findData(selected)))
        self.tts_voice.blockSignals(False)
        edge=provider=='edge'
        for widget in [self.tts_voice,self.rate_controls,self.pitch_controls]:
            widget.setVisible(edge)
            self.voice_form.labelForField(widget).setVisible(edge)
        for widget in [self.google_slow]:
            widget.setVisible(not edge)
            label=self.voice_form.labelForField(widget)
            if label is not None:
                label.setVisible(not edge)
        samples={'it':'Ciao, sono Yun Jin.',
                 'en':'Hello, I am Yun Jin.',
                 'zh-CN':'你好，我是云堇。别忘了休息一下。'}
        self.tts_test.setText(samples[language])

    def save_voice(self):
        self.pet.speech.set_pref('voice_'+self.tts_language.currentData(),self.tts_voice.currentData())

    def reset_voice(self):
        self.pet.speech.set_pref('voice_it','it-IT-ElsaNeural')
        self.provider.setCurrentIndex(self.provider.findData('edge'))
        self.tts_language.setCurrentIndex(self.tts_language.findData('it'))
        self.voice_options()
        self.tts_rate.setValue(20);self.tts_pitch.setValue(15);self.tts_volume.setValue(70)
        self.google_slow.setChecked(False); self.tts_reminders.setChecked(True)

    def read_note(self):
        self.save_note()
        text=self.body.textCursor().selectedText().replace('\u2029','\n') or self.body.toPlainText() or self.title.text()
        self.pet.speech.speak(text)

    def set_sound(self, value):
        self.pet.sound.enabled = value
        self.sound_options.setEnabled(value)
        self.pet.store.set_preference('sound_enabled',value)

    def set_interactions(self, value):
        self.pet.sound.interactions = value
        self.pet.store.set_preference('sound_interactions',value)

    def set_volume(self, value):
        self.pet.sound.volume = value/100
        self.pet.store.set_preference('sound_volume',value/100)

    def changed(self):
        if not self.loading:
            self.dirty = True
            self.status.setText('Salvataggio…')
            self.autosave.start(700)

    def autosave_note(self):
        try:
            self.save_note()
        except Exception as exc:
            self.status.setText('Non salvato: ' + str(exc))

    def save_note(self):
        self.autosave.stop()
        if not self.dirty:
            return
        title, body = self.title.text(), self.body.toPlainText()
        if not title.strip() and not body.strip() and not self.note_path and self.note_id is None:
            self.dirty = False
            return
        self.note_id = self.pet.store.save_note(title,body,self.note_path,self.note_id)
        self.dirty = False
        self.status.setText('Salvato')
        self.update_list_item()

    def update_list_item(self):
        if not self.note_id:
            return
        note = self.pet.store.note(self.note_id)
        self.notes_list.blockSignals(True)
        found = None
        for i in range(self.notes_list.count()):
            item = self.notes_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == self.note_id:
                found = item
                break
        if found is None:
            found = QListWidgetItem()
            found.setData(Qt.ItemDataRole.UserRole,self.note_id)
            self.notes_list.insertItem(0,found)
        found.setText(('▧ ' if note['path'] else '') + note['title'])
        self.notes_list.setCurrentItem(found)
        self.notes_list.blockSignals(False)

    def save_clicked(self):
        self.save_note()
        self.pet.saved_feedback()

    def refresh_notes(self, *_):
        if self.loading:
            return
        if hasattr(self,'autosave'):
            self.save_note()
        self.notes_list.blockSignals(True)
        self.notes_list.clear()
        for note in self.pet.store.notes(self.search.text()):
            item=QListWidgetItem(('▧ ' if note['path'] else '') + note['title'])
            item.setData(Qt.ItemDataRole.UserRole,note['id'])
            item.setToolTip(note['body'][:250])
            self.notes_list.addItem(item)
            if note['id']==self.note_id:
                self.notes_list.setCurrentItem(item)
        self.notes_list.blockSignals(False)

    def select_note(self, current, previous):
        if self.loading or current is None:
            return
        target = current.data(Qt.ItemDataRole.UserRole)
        self.save_note()
        self.load_note(target)

    def load_note(self, note_id):
        note=self.pet.store.note(note_id)
        if note is None:
            return
        self.loading=True
        self.note_id=note_id
        self.note_path=note['path']
        self.title.setText(note['title'])
        self.body.setPlainText(note['body'])
        self.dirty=False
        self.loading=False
        self.show_material()
        self.status.setText('Salvato')
        self.refresh_notes()

    def new_note(self):
        self.save_note()
        self.loading=True
        self.note_id=None
        self.note_path=''
        self.title.clear()
        self.body.clear()
        self.notes_list.clearSelection()
        self.loading=False
        self.dirty=False
        self.show_material()
        self.tabs.setCurrentIndex(0)
        self.body.setFocus()
        self.status.setText('')

    def resolved_path(self):
        if self.note_path.startswith('attachment:'):
            return self.pet.store.root/'attachments'/Path(self.note_path.split(':',1)[1]).name
        return Path(self.note_path) if self.note_path else None

    def show_material(self):
        path=self.resolved_path()
        self.open_file.setVisible(path is not None)
        self.path_label.setText(('Immagine' if self.note_path.startswith('attachment:') else path.name) if path else '')
        self.path_label.setToolTip(str(path) if path else '')
        self.preview.clear()
        self.preview.hide()
        if path and path.is_file() and path.stat().st_size<25*1024*1024:
            reader=QImageReader(str(path))
            size=reader.size()
            if size.isValid():
                size.scale(350,150,Qt.AspectRatioMode.KeepAspectRatio)
                reader.setScaledSize(size)
                image=reader.read()
                if not image.isNull():
                    self.preview.setPixmap(QPixmap.fromImage(image))
                    self.preview.show()

    def open_material(self):
        path=self.resolved_path()
        if path and path.exists():
            self.pet.open_external(QUrl.fromLocalFile(str(path)),self)
        else:
            Messages.information(self,'Materiale non trovato','Il file è stato spostato o eliminato.')

    def delete_note(self):
        if not self.note_id:
            self.new_note()
            return
        if Messages.question(self,'Elimina appunto','Eliminare l’appunto? Il file collegato rimane.') != QMessageBox.StandardButton.Yes:
            return
        self.autosave.stop()
        self.pet.store.delete_note(self.note_id)
        self.dirty=False
        self.new_note()
        self.refresh_notes()

    def add_file(self):
        files=choose_files(self,'Aggiungi file')
        if files:
            self.pet.add_paths(files)

    def add_folder(self):
        folders=choose_files(self,'Aggiungi cartella',mode='folder')
        folder=folders[0] if folders else ''
        if folder:
            self.pet.add_paths([folder])

    def ask_ai(self):
        self.save_note()
        selected=self.body.textCursor().selectedText().replace('\u2029','\n')
        text=selected or self.body.toPlainText()
        instruction=['Spiega questo contenuto in modo chiaro e preciso.',
                     'Traduci questo contenuto in italiano, preservando significato e tono.',
                     'Rivedi questo testo e proponi una versione migliorata, spiegando brevemente le modifiche.',
                     self.question.text().strip() or 'Aiutami a capire questo contenuto.'][self.ai_mode.currentIndex()]
        if self.question.text().strip() and self.ai_mode.currentIndex()!=3:
            instruction+='\n'+self.question.text().strip()
        material=self.resolved_path()
        if not text.strip() and material is None:
            self.status.setText('Aggiungi testo o un file.')
            return
        prompt=instruction+'\n\n'+text
        if material:
            prompt+='\n\nMateriale a cui mi riferisco: '+material.name+' (da allegare a questa conversazione).'
        QApplication.clipboard().setText(prompt.strip())
        self.pet.open_external(QUrl('https://chatgpt.com/'),self)
        self.status.setText('Incolla in ChatGPT.'+(' Allega anche il file.' if material else ''))

    def selected_reminder(self):
        item=self.reminders.currentItem()
        return item.data(0,Qt.ItemDataRole.UserRole) if item else None

    def refresh_reminders(self, force=False):
        rows=self.pet.store.reminders(self.show_done.isChecked())
        signature=repr(rows)
        if signature==self.reminder_signature and not force:
            return
        selected=self.selected_reminder()
        self.reminder_signature=signature
        self.reminders.clear()
        for reminder in rows:
            status={'pending':'In attesa','due':'Da gestire','done':'Completato'}[reminder['status']]
            item=QTreeWidgetItem([reminder['title'],datetime.fromtimestamp(reminder['due']).strftime('%d/%m/%Y %H:%M'),status])
            item.setData(0,Qt.ItemDataRole.UserRole,reminder['id'])
            self.reminders.addTopLevelItem(item)
            if reminder['id']==selected:
                self.reminders.setCurrentItem(item)
        count=sum(r['status']=='due' for r in rows)
        self.nav[(1,None)].setText('Promemoria'+(f' · {count}' if count else ''))
        self.reminder_actions.setEnabled(self.selected_reminder() is not None)

    def complete_reminder(self):
        rid=self.selected_reminder()
        if rid:
            self.pet.complete_reminder(rid)

    def snooze_reminder(self):
        rid=self.selected_reminder()
        if rid:
            self.pet.snooze_reminder(rid,self.snooze_minutes.value())

    def edit_reminder(self):
        rid=self.selected_reminder()
        row=next((r for r in self.pet.store.reminders(True) if r['id']==rid),None)
        if row:
            self.pet.new_reminder(existing=row)

    def delete_reminder(self):
        rid=self.selected_reminder()
        if rid and Messages.question(self,'Elimina promemoria','Eliminare il promemoria?')==QMessageBox.StandardButton.Yes:
            self.pet.store.delete_reminder(rid)
            self.pet.refresh_reminders()

    def backup(self):
        self.save_note()
        files=choose_files(self,'Esporta backup',mode='save',
            filename='YunJin-backup-'+datetime.now().strftime('%Y%m%d')+'.zip',name_filter='ZIP (*.zip)')
        filename=files[0] if files else ''
        if filename:
            self.pet.store.export_backup(filename)
            self.status.setText('Backup salvato.')

    def dragEnterEvent(self,event):
        if self.pet.accepts_mime(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self,event):
        self.pet.capture_mime(event.mimeData())
        event.acceptProposedAction()

    def closeEvent(self,event):
        try:
            self.save_note()
        except Exception as exc:
            Messages.warning(self,'Appunto non salvato',str(exc))
            event.ignore()
            return
        if sys.platform!='darwin' and self.pet.character_hidden and not self.pet.has_tray_access():
            self.showMinimized()
        else:self.hide()
        event.ignore()
        self.pet.panel_closed()
