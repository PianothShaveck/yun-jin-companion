# SPDX-License-Identifier: GPL-3.0-or-later
"""Small reusable study widgets; bounded images and explicit audio playback."""
import html
import json
from pathlib import Path
import time
from PyQt6 import sip
from PyQt6.QtCore import Qt, QUrl, QSize
from PyQt6.QtGui import QImageReader, QTextDocument
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTextBrowser, QDialog,
    QFormLayout, QLineEdit, QSpinBox, QDoubleSpinBox, QCheckBox, QComboBox, QTextEdit,
    QListWidget, QListWidgetItem, QDialogButtonBox, QTabWidget)
from yun_jin_ui import STYLE, plain_label, button, icon_button, scroll_page
from yun_jin_dialogs import choose_files, exec_dialog
from yun_jin_srs import render_cloze, validate_content, validate_settings


class CardDocument(QTextDocument):
    def loadResource(self,kind,name):
        return self.parent().loadResource(kind,name)


class CardBrowser(QTextBrowser):
    def __init__(self):
        super().__init__();self.resources={}
        self.setOpenLinks(False);self.setOpenExternalLinks(False)
        self.setFrameShape(self.Shape.NoFrame)
        self.setStyleSheet('QTextBrowser {background:transparent;border:none;padding:16px;}')
        self.reset_document()
        self.setAccessibleName('Flashcard')

    def reset_document(self):
        # QTextDocument caches image resources across setHtml(). A fresh,
        # owned document avoids both stale images and an unbounded media cache.
        old=self.document();document=CardDocument(self);document.setDefaultFont(self.font())
        document.setDefaultStyleSheet('body {color:#eeeaf4;font-size:27px;text-align:center;} p {margin:16px 0;}')
        self.setDocument(document)
        if not sip.isdeleted(old):old.deleteLater()

    def loadResource(self,kind,name):
        if kind!=QTextDocument.ResourceType.ImageResource or name.toString() not in self.resources: return None
        path=self.resources[name.toString()]
        try:
            if Path(path).stat().st_size>32*1024*1024: return None
            reader=QImageReader(str(path));reader.setAutoTransform(True);size=reader.size()
            if bytes(reader.format()).lower() not in (b'png',b'jpeg',b'jpg',b'gif',b'webp'):return None
            if not size.isValid() or size.width()*size.height()>16000000: return None
            reader.setScaledSize(size.scaled(QSize(520,270),Qt.AspectRatioMode.KeepAspectRatio))
            return reader.read()
        except (OSError,ValueError): return None


class CardFace(QWidget):
    def __init__(self,pet):
        super().__init__();self.pet=pet;self.player=None;self.output=None
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(8)
        self.browser=CardBrowser();layout.addWidget(self.browser,1)
        self.audio_row=QHBoxLayout();self.audio_row.setSpacing(10);layout.addLayout(self.audio_row)
        self.status=plain_label('','alert');self.status.hide();layout.addWidget(self.status)

    def clear_audio(self):
        if self.player: self.player.stop()
        while self.audio_row.count():
            item=self.audio_row.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def present(self,row,answer=False,external=False):
        self.clear_audio();self.status.hide()
        if external:
            text=html.escape(row['back'] if answer else row['front']).replace('\n','<br>')
            paths=row['back_paths'] if answer else row['front_paths']
        else:
            content=json.loads(row['content']) if isinstance(row['content'],str) else row['content']
            front=render_cloze(content['front'],row['ordinal'],answer) if row['kind']=='cloze' else html.escape(content['front']).replace('\n','<br>')
            back=html.escape(content['back']).replace('\n','<br>')
            text=front if not answer else (front+'<hr><p>'+back+'</p>' if back else front)
            files=content['front_media']+(content['back_media'] if answer else [])
            paths=[str(self.pet.store.study.media_path(filename)) for filename in files]
        self.browser.resources={};images=[];audio=[]
        for index,path in enumerate(paths):
            if Path(path).suffix.lower() in ('.png','.jpg','.jpeg','.gif','.webp'):
                url='yjmedia:/'+str(index);self.browser.resources[url]=path
                images.append('<p><img src="'+url+'"></p>')
            else: audio.append(path)
        self.browser.reset_document()
        self.browser.setHtml('<html><body><p>'+text+'</p>'+''.join(images)+'</body></html>')
        self.browser.moveCursor(self.browser.textCursor().MoveOperation.Start)
        self.audio_row.addStretch()
        for index,path in enumerate(audio):
            play=button('Audio'+(f' {index+1}' if len(audio)>1 else ''),lambda checked=False,p=path:self.play(p),self.audio_row,glyph='voice')
            play.setToolTip(Path(path).name)
        self.audio_row.addStretch()

    def play(self,path):
        if not self.pet.sound.enabled or time.time()<self.pet.sound.quiet_until:
            self.status.setText('Suoni disattivati');self.status.show();return
        try:
            from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
            if self.player is None:
                self.player=QMediaPlayer(self);self.output=QAudioOutput(self)
                self.player.setAudioOutput(self.output)
                self.player.errorOccurred.connect(lambda *_:self.audio_error())
            self.output.setVolume(max(0.,min(1.,self.pet.sound.volume)))
            self.player.setSource(QUrl.fromLocalFile(str(path)));self.player.play()
        except Exception: self.audio_error()

    def audio_error(self):
        self.status.setText('Audio non disponibile');self.status.show()

    def hideEvent(self,event):
        if self.player: self.player.stop()
        super().hideEvent(event)


class DeckDialog(QDialog):
    def __init__(self,pet,deck_id=None,parent=None):
        super().__init__(parent);self.pet=pet;self.deck_id=deck_id
        self.setWindowTitle('Mazzo');self.setStyleSheet(STYLE);self.resize(590,580)
        self.deck=pet.store.study.deck(deck_id) if deck_id else None
        from yun_jin_srs import DEFAULTS
        settings=self.deck['settings'] if self.deck else DEFAULTS
        main=QVBoxLayout(self);main.setContentsMargins(20,20,20,18);main.setSpacing(14)
        content=QWidget();layout=QVBoxLayout(content);layout.setSpacing(18)
        self.name=QLineEdit(self.deck['name'] if self.deck else '');self.name.setPlaceholderText('Nome del mazzo')
        self.name.setAccessibleName('Nome del mazzo');self.name.setMaxLength(120);layout.addWidget(self.name)
        self.fsrs=QCheckBox('FSRS');self.fsrs.setChecked(settings['fsrs']);layout.addWidget(self.fsrs)
        form=QFormLayout();form.setHorizontalSpacing(24);form.setVerticalSpacing(14)
        self.retention=QDoubleSpinBox();self.retention.setRange(70,99);self.retention.setDecimals(1)
        self.retention.setSuffix(' %');self.retention.setValue(settings['retention']*100)
        self.retention.setToolTip('Probabilità di ricordare una carta alla sua scadenza. Più alta richiede più ripassi.')
        form.addRow('Ritenzione desiderata',self.retention)
        self.new_limit=self.limit(settings['new_limit']);form.addRow('Nuove al giorno',self.new_limit)
        self.review_limit=self.limit(settings['review_limit']);form.addRow('Ripassi al giorno',self.review_limit)
        self.learning=QLineEdit(settings['learning']);self.relearning=QLineEdit(settings['relearning'])
        for edit in (self.learning,self.relearning):
            edit.setToolTip('Passi separati da spazi: s = secondi, m = minuti, h = ore, d = giorni. Senza unità: minuti. Vuoto: intervalli FSRS.')
        form.addRow('Passi nuove carte',self.learning);form.addRow('Passi dopo un errore',self.relearning)
        self.threshold=QSpinBox();self.threshold.setRange(2,1000);self.threshold.setValue(settings['leech_threshold'])
        self.threshold.setToolTip('Numero di errori nei ripassi che segna una carta come “passaggio ostinato”.')
        form.addRow('Passaggio ostinato dopo',self.threshold);self.threshold.setSuffix(' errori')
        layout.addLayout(form)
        self.suspend=QCheckBox('Metti in pausa i passaggi ostinati');self.suspend.setChecked(settings['suspend_leeches'])
        layout.addWidget(self.suspend)
        self.fsrs.toggled.connect(self.update_fsrs);self.update_fsrs()
        layout.addStretch();main.addWidget(scroll_page(content),1)
        self.error=plain_label('','alert');self.error.hide();main.addWidget(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('Salva');buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Annulla')
        buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);main.addWidget(buttons)

    @staticmethod
    def limit(value):
        spin=QSpinBox();spin.setRange(-1,1000000);spin.setSpecialValueText('Senza limiti');spin.setValue(-1 if value is None else value)
        return spin

    def update_fsrs(self):
        self.retention.setEnabled(self.fsrs.isChecked())

    def save(self):
        settings=dict(fsrs=self.fsrs.isChecked(),retention=self.retention.value()/100,
            new_limit=None if self.new_limit.value()==-1 else self.new_limit.value(),
            review_limit=None if self.review_limit.value()==-1 else self.review_limit.value(),
            learning=self.learning.text(),relearning=self.relearning.text(),leech_threshold=self.threshold.value(),
            suspend_leeches=self.suspend.isChecked())
        try:
            if not self.name.text().strip():
                self.name.setFocus();raise ValueError('Il nome del mazzo non può essere vuoto.')
            validate_settings(settings)
            self.deck_id=self.pet.store.study.save_deck(self.name.text(),settings,self.deck_id)
        except Exception as exc:
            self.error.setText(str(exc));self.error.show();return
        self.accept()


class NoteEditor(QDialog):
    def __init__(self,pet,deck_id,note_id=None,parent=None):
        super().__init__(parent);self.pet=pet;self.deck_id=deck_id;self.note_id=note_id
        self.study=pet.store.study;self.setWindowTitle('Modifica carta' if note_id else 'Nuova carta')
        self.setStyleSheet(STYLE);self.resize(800,660);self.setMinimumSize(600,510)
        note=self.study.note(note_id) if note_id else None
        content=note['content'] if note else dict(front='',back='',front_media=[],back_media=[])
        self.media={side:list(content[side+'_media']) for side in ('front','back')}
        layout=QVBoxLayout(self);layout.setContentsMargins(22,20,22,18);layout.setSpacing(14)
        top=QHBoxLayout();top.setSpacing(12)
        self.kind=QComboBox();self.kind.addItem('Fronte / retro','basic');self.kind.addItem('Cloze','cloze')
        self.kind.setCurrentIndex(1 if note and note['kind']=='cloze' else 0);self.kind.setAccessibleName('Tipo di carta')
        top.addWidget(self.kind);top.addStretch()
        self.cloze_button=button('Lacuna',self.insert_cloze,top,glyph='plus')
        self.cloze_button.setToolTip('Seleziona il testo da nascondere. Esempio: {{c1::你好::saluto}}')
        button('Anteprima',self.preview,top);layout.addLayout(top)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1);self.edits={};self.lists={}
        for side,label in (('front','Fronte'),('back','Retro')):
            page=QWidget();page_layout=QVBoxLayout(page);page_layout.setContentsMargins(0,12,0,0);page_layout.setSpacing(12)
            edit=QTextEdit();edit.setAcceptRichText(False);edit.setPlainText(content[side]);edit.setAccessibleName(label)
            edit.setStyleSheet('QTextEdit {font-size:22px;padding:16px;}');page_layout.addWidget(edit,1);self.edits[side]=edit
            files=QListWidget();files.setMaximumHeight(105);files.setAccessibleName('Allegati '+label.lower())
            page_layout.addWidget(files);self.lists[side]=files
            row=QHBoxLayout();row.setSpacing(12)
            button('Immagine',lambda checked=False,s=side:self.add_media(s,'image'),row,glyph='file')
            button('Audio',lambda checked=False,s=side:self.add_media(s,'audio'),row,glyph='voice');row.addStretch()
            icon_button('close','Rimuovi allegato',lambda s=side:self.remove_media(s),row)
            page_layout.addLayout(row);self.tabs.addTab(page,label);self.refresh_media(side)
        self.kind.currentIndexChanged.connect(self.update_kind);self.update_kind()
        self.error=plain_label('','alert');self.error.hide();layout.addWidget(self.error)
        row=QHBoxLayout();row.setSpacing(12);row.addStretch()
        button('Annulla',self.reject,row,role='quiet')
        if not note_id: button('Salva e aggiungi',lambda:self.save(keep=True),row)
        button('Salva',self.save,row,role='primary');layout.addLayout(row)

    def update_kind(self):
        self.cloze_button.setVisible(self.kind.currentData()=='cloze')
        self.edits['front'].setPlaceholderText('{{c1::你好::saluto}}' if self.kind.currentData()=='cloze' else 'Domanda')
        self.edits['back'].setPlaceholderText('Informazioni aggiuntive' if self.kind.currentData()=='cloze' else 'Risposta')

    def content(self):
        return dict(front=self.edits['front'].toPlainText(),back=self.edits['back'].toPlainText(),
                    front_media=self.media['front'],back_media=self.media['back'])

    def insert_cloze(self):
        import re
        self.tabs.setCurrentIndex(0);edit=self.edits['front'];cursor=edit.textCursor()
        numbers=[int(v) for v in re.findall(r'\{\{c(\d+)::',edit.toPlainText())]
        number=max(numbers,default=0)+1
        if number>99:
            self.error.setText('Massimo 99 numeri di lacuna per nota.');self.error.show();return
        text=cursor.selectedText().replace('\u2029','\n') or 'testo'
        cursor.insertText('{{c'+str(number)+'::'+text+'}}');edit.setTextCursor(cursor);edit.setFocus()

    def refresh_media(self,side):
        self.lists[side].clear()
        for filename in self.media[side]:
            row=self.study.db.execute('SELECT original_name FROM sr_media WHERE filename=?',(filename,)).fetchone()
            self.lists[side].addItem(row[0] if row else filename)
        self.lists[side].setVisible(bool(self.media[side]))

    def add_media(self,side,kind):
        file_filter='Immagini (*.png *.jpg *.jpeg *.gif *.webp)' if kind=='image' else 'Audio (*.wav *.mp3 *.ogg *.m4a *.flac)'
        files=choose_files(self,'Aggiungi '+('immagine' if kind=='image' else 'audio'),name_filter=file_filter)
        try:
            if len(files)+len(self.media[side])>12: raise ValueError('Massimo 12 allegati per lato.')
            imported=[self.study.import_media(path) for path in files]
            self.media[side].extend(filename for filename in imported if filename not in self.media[side]);self.refresh_media(side)
        except Exception as exc: self.error.setText(str(exc));self.error.show()

    def remove_media(self,side):
        index=self.lists[side].currentRow()
        if index>=0: self.media[side].pop(index);self.refresh_media(side)

    def preview(self):
        try: content,ordinals=validate_content(self.kind.currentData(),self.content())
        except ValueError as exc: self.error.setText(str(exc));self.error.show();return
        dialog=QDialog(self);dialog.pet=self.pet;dialog.setWindowTitle('Anteprima');dialog.setStyleSheet(STYLE);dialog.resize(650,550)
        layout=QVBoxLayout(dialog);face=CardFace(self.pet);layout.addWidget(face,1)
        row=dict(kind=self.kind.currentData(),content=content,ordinal=ordinals[0])
        face.present(row)
        controls=QHBoxLayout();controls.setSpacing(12)
        if len(ordinals)>1:
            select=QComboBox()
            for ordinal in ordinals: select.addItem(f'Lacuna {ordinal}',ordinal)
            def select_cloze():
                row['ordinal']=select.currentData();face.present(row,show.isChecked())
            select.currentIndexChanged.connect(select_cloze);controls.addWidget(select)
        controls.addStretch();show=button('Risposta',None,controls);show.setCheckable(True)
        show.toggled.connect(lambda answer:face.present(row,answer));button('Chiudi',dialog.accept,controls);layout.addLayout(controls)
        try: exec_dialog(dialog,self.pet)
        finally: face.clear_audio();dialog.deleteLater()

    def save(self,checked=False,keep=False):
        try:
            self.note_id=self.study.save_note(self.deck_id,self.kind.currentData(),self.content(),self.note_id)
        except Exception as exc: self.error.setText(str(exc));self.error.show();return
        if not keep: self.accept();return
        self.note_id=None;self.error.hide()
        for side in ('front','back'): self.edits[side].clear();self.media[side]=[];self.refresh_media(side)
        self.tabs.setCurrentIndex(0);self.edits['front'].setFocus()
