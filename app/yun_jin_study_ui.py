# SPDX-License-Identifier: GPL-3.0-or-later
"""Deck browser and fast native review, with no web engine."""
import json
from pathlib import Path
import time
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (QWidget,QDialog,QVBoxLayout,QHBoxLayout,QComboBox,QLineEdit,
    QTreeWidget,QTreeWidgetItem,QHeaderView,QCheckBox,QMenu,QMessageBox,QDialogButtonBox)
from yun_jin_ui import STYLE,plain_label,button,icon_button,menu_button,card
from yun_jin_dialogs import Messages,choose_files,exec_dialog,owner_window
from yun_jin_srs import duration_label
from yun_jin_study_widgets import CardFace,DeckDialog,NoteEditor


class ReviewDialog(QDialog):
    def __init__(self,pet,deck_id=None,quick_cards=None,external=None,parent=None):
        super().__init__(parent or owner_window(pet));self.pet=pet;self.study=pet.store.study
        self.deck_id=deck_id;self.external=external is not None;self.external_cards=list(external or [])
        self.quick_ids=[c['id'] for c in quick_cards] if quick_cards is not None else None
        self.session=None if self.external else self.study.start_session(deck_id,'quick' if quick_cards is not None else 'study')
        self.finished_session=False;self.row=None;self.answer=False;self.prefer_new=False
        self.answered=0;self.history=[];self.started=time.monotonic();self.revealed_at=0
        self.setWindowTitle('Ripasso Anki' if self.external else 'Studio');self.setStyleSheet(STYLE)
        self.resize(720,580);self.setMinimumSize(590,460)
        main=QVBoxLayout(self);main.setContentsMargins(24,20,24,22);main.setSpacing(16)
        head=QHBoxLayout();head.setSpacing(12)
        name='Anki · esercizio libero' if self.external else (self.study.deck(deck_id)['name'] if deck_id else 'Ripasso rapido')
        self.title=plain_label(name,'section');head.addWidget(self.title,1)
        self.progress=plain_label('','muted');head.addWidget(self.progress)
        self.undo_button=icon_button('reset','Annulla ultima risposta',self.undo,head);self.undo_button.setVisible(not self.external)
        button('Termina',self.close,head,role='quiet');main.addLayout(head)
        self.hero,hero_layout=card(main,hero=True)
        self.face=CardFace(pet);hero_layout.addWidget(self.face,1)
        main.setStretchFactor(self.hero,1)
        self.message=plain_label('','section');self.message.setAlignment(Qt.AlignmentFlag.AlignCenter);hero_layout.addWidget(self.message);self.message.hide()
        self.detail=plain_label('','muted');self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter);main.addWidget(self.detail)
        self.reveal_button=button('Mostra risposta',self.reveal,main,role='primary')
        self.reveal_button.setToolTip('Spazio')
        self.rating_box=QWidget();ratings=QHBoxLayout(self.rating_box);ratings.setContentsMargins(0,0,0,0);ratings.setSpacing(10)
        self.rating_buttons={}
        for number,label in enumerate(('Da rivedere','Difficile','Bene','Facile'),1):
            b=button(label,lambda checked=False,n=number:self.rate(n),ratings,role='primary' if number==3 else '')
            b.setToolTip(str(number));self.rating_buttons[number]=b
        main.addWidget(self.rating_box)
        self.external_next=button('Avanti',self.advance_external,main,role='primary');self.external_next.hide()
        self.done_button=button('Torna ai mazzi' if not self.external else 'Fatto',self.close,main,role='primary');self.done_button.hide()
        self.shortcuts=[]
        for key,callback in [('Space',self.space),('1',lambda:self.rate(1)),('2',lambda:self.rate(2)),
                             ('3',lambda:self.rate(3)),('4',lambda:self.rate(4)),('Ctrl+Z',self.undo)]:
            shortcut=QShortcut(QKeySequence(key),self);shortcut.activated.connect(callback);self.shortcuts.append(shortcut)
        self.wait_timer=QTimer(self);self.wait_timer.setInterval(1000);self.wait_timer.timeout.connect(self.wait_tick)
        self.next_card()

    def next_card(self,restored=None):
        self.wait_timer.stop();self.answer=False;self.detail.clear();self.message.hide();self.face.show();self.done_button.hide()
        self.rating_box.hide();self.external_next.hide();self.reveal_button.show()
        self.undo_button.setEnabled(bool(self.history))
        if not self.external and self.deck_id is not None:
            try:self.study.deck(self.deck_id)
            except ValueError:
                self.row=None;self.finish_session();self.face.hide();self.reveal_button.hide()
                self.message.setText('Mazzo archiviato');self.message.show();self.done_button.show();self.undo_button.setEnabled(False)
                return
        if self.external:
            self.row=self.external_cards[0] if self.external_cards else None
        elif restored is not None:
            self.row=self.study.card(restored)
        elif self.quick_ids is not None:
            self.row=None
            while self.quick_ids and self.row is None:
                ident=self.quick_ids.pop(0)
                try:
                    candidate=self.study.card(ident)
                    cap=self.study.deck(candidate['deck_id'])['settings']['review_limit']
                    allowed=cap is None or self.study.usage(candidate['deck_id'],time.time())['reviews']<cap
                    if allowed and not candidate['suspended'] and candidate['last_review'] is not None and candidate['last_review']<=time.time()-1800:self.row=candidate
                except ValueError: pass
        else:
            self.row=self.study.next_card(self.deck_id,self.prefer_new)
        if self.row is None:
            due=self.study.next_learning_due(self.deck_id) if self.deck_id and self.quick_ids is None else None
            if due is not None and 0<due-time.time()<=60:
                self.face.hide();self.reveal_button.hide();self.message.show();self.wait_tick();self.wait_timer.start();return
            self.finish_session()
            self.face.hide();self.message.show();self.reveal_button.hide();self.done_button.show()
            self.message.setText('Sessione completata' if self.answered else 'Nessuna carta in scadenza')
            if due is not None and due>time.time(): self.detail.setText('Prossima carta tra '+duration_label(due-time.time()))
            else: self.detail.setText(f'{self.answered} risposte' if self.answered else '')
            return
        self.progress.setText(f'{self.answered} '+('risposta' if self.answered==1 else 'risposte') if self.answered else '')
        self.face.present(self.row,external=self.external);self.started=time.monotonic();self.reveal_button.setFocus()
        if self.external or self.quick_ids is not None:
            self.pet.study_tools.remember_practice([self.row],self.external)

    def wait_tick(self):
        if self.finished_session: self.wait_timer.stop();return
        try:self.study.deck(self.deck_id)
        except ValueError:self.next_card();return
        due=self.study.next_learning_due(self.deck_id)
        if due is None or due<=time.time(): self.next_card();return
        self.message.setText('Prossima carta tra '+duration_label(due-time.time()))

    def reveal(self):
        if self.row is None or self.answer or self.finished_session: return
        if not self.current_card_valid():return
        now=time.time()
        if not self.external:
            try:
                if self.row['last_review'] is not None and now<self.row['last_review']:
                    raise ValueError('Controlla l’orologio di sistema prima di continuare.')
                predictions={n:self.study.predict(self.row,n,now) for n in self.rating_buttons}
            except Exception as exc:
                self.detail.setText(str(exc));return
        self.answer=True;self.revealed_at=time.monotonic();self.face.present(self.row,True,self.external)
        if self.external or self.quick_ids is not None:
            self.pet.study_tools.remember_practice([self.row],self.external,reviewed=True)
        self.reveal_button.hide()
        if self.external:
            self.external_next.show();return
        for number,b in self.rating_buttons.items():
            predicted=predictions[number]
            label=('Da rivedere','Difficile','Bene','Facile')[number-1]
            b.setText(label+'\n'+duration_label(predicted['due']-now))
        self.rating_box.show()

    def current_card_valid(self):
        if self.external:return True
        try:current=self.study.card(self.row['id'])
        except ValueError:self.next_card();return False
        if current['suspended']:
            self.next_card();return False
        if current['revision']!=self.row['revision']:
            self.next_card(restored=current['id']);self.detail.setText('Carta modificata. Rileggi il fronte.');return False
        return True

    def space(self):
        if not self.answer: self.reveal()
        elif self.external: self.advance_external()
        else: self.rate(3)

    def rate(self,rating):
        if self.external or not self.answer or self.row is None or self.finished_session: return
        if time.monotonic()-self.revealed_at<.2: return
        if not self.current_card_valid():return
        try:
            _,after=self.study.review(self.row['id'],rating,self.session,self.row['revision'],
                duration_ms=int((time.monotonic()-self.started)*1000))
        except Exception as exc:
            Messages.warning(self,'Risposta non salvata',str(exc));return
        self.history.append(self.row['id']);self.answered+=1
        # Alternate NEW/REVIEW without disturbing due learning steps.
        if self.row['state']==0: self.prefer_new=False
        elif self.row['state']==2: self.prefer_new=True
        self.next_card()

    def undo(self):
        if self.external or not self.history: return
        try: ident=self.study.undo(self.session)
        except Exception as exc: Messages.warning(self,'Annulla risposta',str(exc));return
        if ident is None: return
        if self.finished_session:
            with self.study.db:self.study.db.execute("UPDATE sr_sessions SET ended=NULL WHERE id=?",(self.session,))
            self.finished_session=False
        if self.quick_ids is not None and self.row is not None and self.row['id']!=ident:
            self.quick_ids.insert(0,self.row['id'])
        self.history.pop();self.answered=max(0,self.answered-1);self.next_card(restored=ident)

    def advance_external(self):
        if not self.external or not self.answer or time.monotonic()-self.revealed_at<.2: return
        self.external_cards.pop(0);self.answered+=1;self.next_card()

    def finish_session(self):
        if self.finished_session: return
        self.finished_session=True;self.wait_timer.stop();self.face.clear_audio()
        self.progress.clear()
        if self.session:
            decks=self.study.end_session(self.session)
            self.pet.study_tools.optimize(decks)
        self.undo_button.setEnabled(bool(self.history))

    def closeEvent(self,event):
        self.finish_session();self.pet.study_tools.review_closed(self);super().closeEvent(event)

    def reject(self):
        self.close()


class StudyPanel(QWidget):
    def __init__(self,pet):
        super().__init__();self.pet=pet;self.study=pet.store.study;self.offset=0
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(16)
        top=QHBoxLayout();top.setSpacing(12)
        self.deck_choice=QComboBox();self.deck_choice.setAccessibleName('Mazzo');self.deck_choice.setMinimumWidth(190)
        top.addWidget(self.deck_choice,1);self.deck_space=QWidget();top.addWidget(self.deck_space,1)
        button('Nuovo mazzo',self.new_deck,top,glyph='plus')
        more=QMenu(self);more.addAction('Opzioni del mazzo…',self.deck_options)
        more.addAction('Richiami e Anki…',self.study_settings);more.addSeparator();more.addAction('Archivia mazzo',self.archive)
        archived_action=more.addAction('Mazzi archiviati…',self.archived)
        more.aboutToShow.connect(lambda:archived_action.setEnabled(bool(self.study.db.execute('SELECT 1 FROM sr_decks WHERE archived=1 LIMIT 1').fetchone())))
        menu_button('',more,top);layout.addLayout(top)
        self.hero,hero_layout=card(layout,hero=True)
        metrics=QHBoxLayout();metrics.setSpacing(28)
        self.metrics={}
        for key,label in [('new','Nuove'),('reviews','Ripassi'),('learning','In apprendimento')]:
            column=QVBoxLayout();number=plain_label('0','metric');number.setStyleSheet('font-size:36px;')
            column.addWidget(number);column.addWidget(plain_label(label,'muted'));metrics.addLayout(column);self.metrics[key]=number
        metrics.addStretch();hero_layout.addLayout(metrics)
        row=QHBoxLayout();row.setSpacing(12)
        self.study_button=button('Studia',self.start,row,glyph='play',role='primary')
        self.today=plain_label('','muted');row.addWidget(self.today,1);hero_layout.addLayout(row)
        self.collection_area=QWidget();collection=QVBoxLayout(self.collection_area)
        collection.setContentsMargins(0,0,0,0);collection.setSpacing(16);layout.addWidget(self.collection_area,1)
        tools=QHBoxLayout();tools.setSpacing(12)
        self.add_button=button('Aggiungi carta',self.add,tools,glyph='plus')
        self.search=QLineEdit();self.search.setPlaceholderText('Cerca carte');self.search.setClearButtonEnabled(True);tools.addWidget(self.search,1)
        self.ostinati=QCheckBox('Passaggi ostinati');self.ostinati.setToolTip('Carte che hanno raggiunto la soglia di errori del mazzo.')
        tools.addWidget(self.ostinati);collection.addLayout(tools)
        self.cards=QTreeWidget();self.cards.setRootIsDecorated(False);self.cards.setHeaderLabels(['Fronte','Carte','Stato'])
        self.cards.header().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        for i in (1,2): self.cards.header().setSectionResizeMode(i,QHeaderView.ResizeMode.ResizeToContents)
        self.cards.itemDoubleClicked.connect(lambda *_:self.edit());collection.addWidget(self.cards,1)
        bottom=QHBoxLayout();bottom.setSpacing(12)
        self.edit_button=button('Modifica',self.edit,bottom)
        actions=QMenu(self);actions.addAction('Metti in pausa / Riattiva',self.toggle_suspend);actions.addAction('Elimina',self.delete)
        menu_button('',actions,bottom);bottom.addStretch()
        self.previous=icon_button('left','Pagina precedente',lambda:self.page(-1),bottom)
        self.next=icon_button('right','Pagina successiva',lambda:self.page(1),bottom)
        collection.addLayout(bottom)
        self.summary=plain_label('','muted');collection.addWidget(self.summary)
        self.empty=plain_label('Crea un mazzo per iniziare.','section')
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter);layout.addWidget(self.empty,1)
        self.search_timer=QTimer(self);self.search_timer.setSingleShot(True);self.search_timer.setInterval(180)
        self.search_timer.timeout.connect(self.filter_changed)
        self.search.textChanged.connect(lambda:self.search_timer.start())
        self.ostinati.toggled.connect(self.filter_changed)
        self.deck_choice.currentIndexChanged.connect(self.filter_changed)
        self.cards.itemSelectionChanged.connect(lambda:self.edit_button.setEnabled(self.selected() is not None))
        self.refresh()

    def deck_id(self): return self.deck_choice.currentData()
    def selected(self):
        item=self.cards.currentItem();return item.data(0,Qt.ItemDataRole.UserRole) if item else None
    def filter_changed(self,*_): self.offset=0;self.refresh_cards()
    def page(self,step): self.offset=max(0,self.offset+100*step);self.refresh_cards()

    def refresh(self,select=None):
        old=select or self.deck_id();self.deck_choice.blockSignals(True);self.deck_choice.clear()
        for deck in self.study.decks(): self.deck_choice.addItem(deck['name'],deck['id'])
        index=self.deck_choice.findData(old)
        if index>=0:self.deck_choice.setCurrentIndex(index)
        self.deck_choice.blockSignals(False);self.refresh_cards()

    def refresh_cards(self):
        deck_id=self.deck_id();has=deck_id is not None;self.empty.setVisible(not has)
        self.deck_choice.setVisible(has);self.deck_space.setVisible(not has);self.collection_area.setVisible(has)
        self.hero.setVisible(has);self.add_button.setEnabled(has);self.search.setEnabled(has);self.ostinati.setEnabled(has)
        self.cards.clear();self.summary.clear();self.edit_button.setEnabled(False)
        if not has:self.previous.setEnabled(False);self.next.setEnabled(False);return
        stats=self.study.counts(deck_id)
        for key,widget in self.metrics.items(): widget.setText(str(stats[key]))
        self.study_button.setEnabled(stats['total']>stats['suspended'])
        self.today.setText(f"{stats['today']} risposte oggi" if stats['today'] else '')
        rows=self.study.browse(deck_id,self.search.text(),self.ostinati.isChecked(),self.offset)
        for row in rows:
            front=row['content']['front'].replace('\n',' ')[:130] or 'Immagine / audio'
            state='In pausa' if row['suspended'] else ('Passaggio ostinato' if row['ostinato'] else '')
            item=QTreeWidgetItem([front,str(row['cards']),state]);item.setData(0,Qt.ItemDataRole.UserRole,row)
            self.cards.addTopLevelItem(item)
        self.previous.setEnabled(self.offset>0);self.next.setEnabled(len(rows)==100)
        text=f"{stats['total']} "+('carta' if stats['total']==1 else 'carte')
        if stats['retention'] is not None:text+=f" · Ritenzione a 30 giorni {stats['retention']:.0%}"
        self.summary.setText(text);self.summary.setToolTip('Ritenzione osservata: risposte ricordate nei ripassi distanziati di almeno un giorno. Non comprende i passi brevi.')

    def new_deck(self):
        dialog=DeckDialog(self.pet,parent=self.window())
        try:
            if exec_dialog(dialog,self.pet): self.refresh(dialog.deck_id)
        finally: dialog.deleteLater()

    def deck_options(self):
        if self.deck_id() is None:return
        dialog=DeckDialog(self.pet,self.deck_id(),self.window())
        try:
            if exec_dialog(dialog,self.pet):self.refresh(dialog.deck_id)
        finally:dialog.deleteLater()

    def add(self): self.editor()
    def edit(self):
        row=self.selected()
        if row:self.editor(row['id'])
    def editor(self,note_id=None):
        if self.deck_id() is None:return
        dialog=NoteEditor(self.pet,self.deck_id(),note_id,self.window())
        try:exec_dialog(dialog,self.pet)
        finally:dialog.deleteLater();self.refresh_cards()
    def toggle_suspend(self):
        row=self.selected()
        if row:self.study.suspend(row['id'],not row['suspended']);self.refresh_cards()
    def delete(self):
        row=self.selected()
        if row and Messages.question(self,'Elimina carta','Eliminare questa carta e le sue lacune?')==QMessageBox.StandardButton.Yes:
            self.study.delete_note(row['id']);self.refresh_cards()
    def archive(self):
        if self.deck_id() is None:return
        if Messages.question(self,'Archivia mazzo','Rimuovere il mazzo dallo studio? I dati restano nel backup.')==QMessageBox.StandardButton.Yes:
            self.study.archive_deck(self.deck_id());self.refresh()
    def archived(self):
        dialog=QDialog(self.window());dialog.pet=self.pet;dialog.setWindowTitle('Mazzi archiviati');dialog.setStyleSheet(STYLE)
        layout=QVBoxLayout(dialog);layout.setContentsMargins(22,22,22,18);layout.setSpacing(16)
        choices=QComboBox()
        for row in self.study.db.execute('SELECT id,name FROM sr_decks WHERE archived=1 ORDER BY name'):
            choices.addItem(row['name'],row['id'])
        layout.addWidget(choices);dialog.resize(440,160)
        def restore():
            if choices.currentData() is not None:
                self.study.restore_deck(choices.currentData());self.refresh(choices.currentData())
            dialog.accept()
        row=QHBoxLayout();row.setSpacing(12);row.addStretch()
        button('Chiudi',dialog.reject,row);button('Ripristina',restore,row,role='primary');layout.addLayout(row)
        try:exec_dialog(dialog,self.pet)
        finally:dialog.deleteLater()

    def start(self):
        if self.deck_id() is not None:self.pet.study_tools.open_review(self.deck_id())
    def study_settings(self):
        dialog=StudySettings(self.pet,self.window())
        try:exec_dialog(dialog,self.pet)
        finally:dialog.deleteLater()

    def showEvent(self,event):
        super().showEvent(event);self.refresh()


class StudySettings(QDialog):
    def __init__(self,pet,parent=None):
        super().__init__(parent);self.pet=pet;self.setWindowTitle('Richiami e Anki');self.setStyleSheet(STYLE);self.resize(570,360)
        layout=QVBoxLayout(self);layout.setContentsMargins(24,22,24,20);layout.setSpacing(18)
        self.enabled=QCheckBox('Richiami durante la giornata');self.enabled.setChecked(pet.study_tools.enabled)
        self.enabled.setToolTip('Ogni 90–150 minuti, al massimo 3 volte al giorno. Solo carte difficili dei mazzi studiati oggi. Nessun richiamo durante il focus.')
        self.enabled.toggled.connect(pet.study_tools.set_enabled);layout.addWidget(self.enabled)
        self.anki=QCheckBox('Includi le carte di Anki');self.anki.setChecked(pet.study_tools.anki_enabled)
        self.anki.setToolTip('Passaggi ostinati e 10% delle carte più difficili dei mazzi studiati oggi. Nessuna risposta viene registrata in Anki.')
        self.anki.toggled.connect(self.set_anki);layout.addWidget(self.anki)
        self.suspended=QCheckBox('Includi passaggi ostinati sospesi');self.suspended.setChecked(pet.study_tools.anki_include_suspended)
        self.suspended.setToolTip('Solo per gli esercizi Anki. Le carte rimangono sospese nella collezione originale.')
        self.suspended.toggled.connect(pet.study_tools.set_anki_suspended)
        suspended_row=QHBoxLayout();suspended_row.setContentsMargins(28,0,0,0);suspended_row.addWidget(self.suspended);layout.addLayout(suspended_row)
        row=QHBoxLayout();row.setSpacing(12)
        self.profiles=QComboBox();self.profiles.setAccessibleName('Profilo Anki');self.profiles.setMinimumWidth(150)
        from yun_jin_anki import find_profiles
        current=pet.study_tools.anki_path
        paths=find_profiles()
        if current and Path(current) not in paths:paths.append(Path(current))
        self.profiles.addItem('Scegli profilo','')
        for path in paths:self.profiles.addItem(path.parent.name,str(path))
        selected=current or (str(paths[0]) if len(paths)==1 else '')
        self.profiles.setCurrentIndex(max(0,self.profiles.findData(selected)))
        self.profiles.currentIndexChanged.connect(self.select_profile);row.addWidget(self.profiles,1)
        button('Sfoglia…',self.browse,row);layout.addLayout(row)
        self.status=plain_label('','muted');layout.addWidget(self.status);self.sync()
        pet.study_tools.anki_changed.connect(self.sync)
        controls=QHBoxLayout();controls.setSpacing(12)
        self.practice_button=button('Ripasso Anki',self.practice,controls,glyph='play')
        button('Aggiorna',lambda:pet.study_tools.refresh_anki(force=True),controls);controls.addStretch();layout.addLayout(controls)
        layout.addStretch();button('Chiudi',self.accept,layout,role='primary')
        self.sync()
        if selected!=current:pet.study_tools.set_anki_path(selected)
        elif selected and pet.study_tools.anki_enabled and time.time()>=pet.study_tools.anki_valid_until:
            pet.study_tools.refresh_anki(force=True)

    def practice(self):
        # The review must not become a child of this short-lived modal dialog.
        self.accept();QTimer.singleShot(0,self.pet.study_tools.open_anki)

    def set_anki(self,value):
        self.pet.study_tools.anki_enabled=value;self.pet.store.set_preference('study_anki_enabled',value)
        if value:self.pet.study_tools.refresh_anki(force=True)
        else:self.pet.study_tools.clear_anki()
    def select_profile(self):
        self.pet.study_tools.set_anki_path(self.profiles.currentData() or '')
    def browse(self):
        from yun_jin_anki import profile_root
        current=self.profiles.currentData()
        directory=Path(current).parent if current else profile_root()
        paths=choose_files(self,'Collezione Anki',filename='collection.anki2',
            name_filter='Anki (collection.anki2)',directory=directory)
        if not paths:return
        path=paths[0];index=self.profiles.findData(path)
        if index<0:self.profiles.addItem(Path(path).parent.name,path);index=self.profiles.count()-1
        self.profiles.setCurrentIndex(index);self.anki.setChecked(True)
    def sync(self):
        self.status.setText(self.pet.study_tools.anki_status)
        self.suspended.setEnabled(self.pet.study_tools.anki_enabled)
        self.status.setToolTip(self.pet.study_tools.anki_detail)
        if hasattr(self,'practice_button'):
            self.practice_button.setEnabled(self.pet.study_tools.anki_enabled and
                bool(self.pet.study_tools.anki_cards or self.pet.study_tools.anki_total))
