"""Interaction and background boundaries, including focus and macOS ownership."""
import json,os,sys,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from PyQt6 import sip
from PyQt6.QtCore import QEvent,QEventLoop,QTimer,Qt
from PyQt6.QtWidgets import QApplication
from yun_jin_app import Companion
from yun_jin_data import Store
from yun_jin_study_ui import ReviewDialog,StudySettings
from yun_jin_study_widgets import DeckDialog,NoteEditor
from yun_jin_macos import MacOverlay
app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False)


class StudyUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)
        self.store.set_preference('updates_enabled',False);self.pet=Companion(self.store)
        for timer in (self.pet.timer,self.pet.reminder_timer,self.pet.checkpoint_timer,self.pet.study_tools.timer):timer.stop()
        self.pet.context.enabled={k:False for k in ('greeting','time','weather')}
        self.pet.cancel();self.pet.idle();self.pet.mode='normal';self.pet.paused=False
        self.s=self.store.study;self.deck=self.s.save_deck('Cinese')
    def tearDown(self):
        self.pet.close();self.pet.deleteLater();app.processEvents();self.store.close();self.tmp.cleanup()
    def add(self,front='你好',kind='basic'):
        note=self.s.save_note(self.deck,kind,dict(front=front,back='Ciao'))
        return self.s.db.execute('SELECT id FROM sr_cards WHERE note_id=? ORDER BY ordinal',(note,)).fetchone()[0]
    def open(self,**kwargs):
        self.pet.study_tools.open_review(self.deck,**kwargs);app.processEvents();return self.pet.study_tools.active_dialog
    def rate(self,dialog,rating):
        dialog.reveal();dialog.revealed_at-=1;dialog.rate(rating);app.processEvents()
    def wait_until(self,predicate,timeout=5):
        limit=time.monotonic()+timeout
        while not predicate() and time.monotonic()<limit:
            loop=QEventLoop();QTimer.singleShot(20,loop.quit);loop.exec()
        self.assertTrue(predicate(),'Async operation timed out')

    def test_anki_worker_deadline_leaves_time_for_snapshot_and_read(self):
        from yun_jin_anki import READ_SECONDS,SNAPSHOT_SECONDS
        self.assertGreater(self.pet.study_tools.anki_timeout.interval(),
                           (READ_SECONDS+SNAPSHOT_SECONDS+1)*1000)

    def test_answer_hidden_ratings_wait_for_reveal_and_undo_final_answer(self):
        cid=self.add();dialog=self.open();self.assertFalse(dialog.rating_box.isVisible())
        dialog.rate(3);self.assertEqual(self.s.card(cid)['reps'],0)
        self.rate(dialog,4);self.assertTrue(dialog.finished_session);self.assertEqual(self.s.card(cid)['reps'],1)
        dialog.undo();self.assertFalse(dialog.finished_session);self.assertEqual(self.s.card(cid)['reps'],0)
        self.assertEqual(dialog.row['id'],cid);self.assertFalse(dialog.answer)

    def test_new_and_review_cards_interleave_and_due_learning_has_priority(self):
        review=self.add('Vecchia');new=self.add('Nuova');sid=self.s.start_session(self.deck)
        self.s.review(review,4,sid,now=time.time()-10*86400);self.s.end_session(sid)
        self.s.db.execute('UPDATE sr_cards SET due=? WHERE id=?',(time.time()-1,review));self.s.db.commit()
        dialog=self.open();self.assertEqual(dialog.row['id'],review)
        self.rate(dialog,3);self.assertEqual(dialog.row['id'],new)
        self.rate(dialog,1);self.assertTrue(dialog.wait_timer.isActive())
        self.s.db.execute('UPDATE sr_cards SET due=? WHERE id=?',(time.time()-1,new));self.s.db.commit()
        dialog.wait_tick();self.assertEqual(dialog.row['id'],new)

    def test_short_session_closure_requests_optimization_and_reopens_saved_progress(self):
        cid=self.add();self.add('世界');dialog=self.open()
        with patch.object(self.pet.study_tools,'optimize') as optimize:
            self.rate(dialog,3);dialog.close();optimize.assert_called_once_with([self.deck])
        self.assertEqual(self.s.card(cid)['state'],1);self.assertIsNone(self.pet.study_tools.active_dialog)
        self.assertIsNotNone(self.open().row)

    def make_hard(self):
        cid=self.add();sid=self.s.start_session(self.deck)
        self.s.review(cid,4,sid,now=time.time()-3600);self.s.end_session(sid)
        self.s.db.execute('UPDATE sr_cards SET difficulty=9,lapses=5,due=? WHERE id=?',(time.time()+86400,cid));self.s.db.commit()
        return cid

    def test_prompts_are_targeted_sparse_dismissable_and_blocked_by_focus(self):
        cid=self.make_hard();tools=self.pet.study_tools;tools.next_prompt=0
        with patch.object(self.pet.context,'can_react',return_value=True):tools.poll()
        self.assertIsNotNone(tools.prompt);self.assertTrue(tools.prompt.isVisible())
        self.assertEqual(tools.prompt.candidates[0]['id'],cid)
        self.assertGreaterEqual(tools.next_prompt-time.time(),89*60)
        tools.prompt.hide();count=self.store.preference('study_prompt_history',{})['count']
        with patch.object(self.pet.context,'can_react',return_value=True):tools.poll()
        self.assertFalse(tools.prompt.isVisible());self.assertEqual(self.store.preference('study_prompt_history',{})['count'],count)
        self.pet.start_focus(25);tools.next_prompt=0
        with patch.object(self.pet.context,'can_react',return_value=True):tools.poll()
        self.assertFalse(tools.prompt.isVisible())

    def test_native_extra_review_is_logged_but_anki_practice_never_enters_native_history(self):
        cid=self.make_hard();tools=self.pet.study_tools;tools.open_review(quick_cards=[self.s.card(cid)])
        dialog=tools.active_dialog;self.rate(dialog,3);self.assertEqual(self.s.card(cid)['reps'],2);dialog.close();app.processEvents()
        before=self.s.db.execute('SELECT count(*) FROM sr_reviews').fetchone()[0]
        tools.anki_enabled=True;tools.anki_valid_until=time.time()+600
        external=dict(id=100,front='你好',back='Ciao',front_paths=[],back_paths=[],last_review=time.time()-3600)
        tools.open_anki(cards=[external]);dialog=tools.active_dialog;dialog.reveal();dialog.revealed_at-=1;dialog.advance_external()
        self.assertTrue(dialog.finished_session);self.assertEqual(self.s.db.execute('SELECT count(*) FROM sr_reviews').fetchone()[0],before)

    def test_editor_saves_cloze_and_validates_before_close(self):
        editor=NoteEditor(self.pet,self.deck);editor.kind.setCurrentIndex(1)
        editor.edits['front'].setPlainText('Senza lacune');editor.save();self.assertIsNone(editor.note_id)
        editor.edits['front'].setPlainText('{{c1::你好}} {{c2::世界}}');editor.save()
        self.assertEqual(self.s.counts(self.deck)['total'],2);editor.deleteLater()
        options=DeckDialog(self.pet,self.deck);self.assertEqual(options.learning.text(),'10s 30s 1m 10m')
        self.assertEqual(options.relearning.text(),'10s 30s 1m');self.assertEqual(options.new_limit.value(),-1)
        self.assertEqual(options.threshold.value(),16);options.deleteLater()

    def test_live_edits_deletions_and_archiving_do_not_grade_stale_cards(self):
        cid=self.add();other=self.add('谢谢');dialog=self.open()
        note_id=self.s.card(cid)['note_id']
        self.s.save_note(self.deck,'basic',dict(front='新しい質問',back='Risposta nuova'),note_id)
        dialog.reveal();self.assertFalse(dialog.answer)
        self.assertIn('新しい質問',dialog.face.browser.toPlainText())
        self.s.delete_note(note_id);dialog.reveal();self.assertEqual(dialog.row['id'],other)
        self.s.archive_deck(self.deck);dialog.reveal()
        self.assertTrue(dialog.finished_session);self.assertEqual(dialog.message.text(),'Mazzo archiviato')
        self.assertEqual(self.s.db.execute('SELECT count(*) FROM sr_reviews').fetchone()[0],0)

    def test_review_from_anki_settings_survives_settings_destruction(self):
        from yun_jin_dialogs import exec_dialog
        self.pet.open_panel(tab=6);app.processEvents();tools=self.pet.study_tools
        tools.anki_enabled=True;tools.anki_valid_until=time.time()+600
        tools.anki_cards=[dict(id=100,front='你好',back='Ciao',front_paths=[],back_paths=[],last_review=time.time()-3600)]
        settings=StudySettings(self.pet,self.pet.panel)
        QTimer.singleShot(0,settings.practice);exec_dialog(settings,self.pet)
        settings.deleteLater();app.processEvents();app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        dialog=tools.active_dialog
        self.assertIsNotNone(dialog);self.assertFalse(sip.isdeleted(dialog));self.assertIs(dialog.parentWidget(),self.pet.panel)
        dialog.reveal();self.assertTrue(dialog.answer)

    def test_destroyed_review_releases_controller_and_closes_session(self):
        self.add();dialog=self.open();session=dialog.session
        dialog.deleteLater();app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.assertIsNone(self.pet.study_tools.active_dialog)
        self.assertIsNotNone(self.s.db.execute('SELECT ended FROM sr_sessions WHERE id=?',(session,)).fetchone()[0])
        self.assertIsNotNone(self.open())

    def test_anki_timeout_cleans_snapshot_and_allows_retry(self):
        tools=self.pet.study_tools
        process=Mock();process.scratch=tempfile.TemporaryDirectory()
        directory=Path(process.scratch.name);(directory/'private-copy').write_text('temporary')
        tools.anki_process=process;tools.anki_requested=True;tools.anki_status='Lettura Anki…'
        tools.anki_timed_out()
        self.assertIsNone(tools.anki_process);self.assertFalse(tools.anki_requested)
        self.assertFalse(directory.exists());self.assertNotIn('Lettura',tools.anki_status)

    def test_anki_background_reader_handles_open_exclusive_collection(self):
        import test_anki_reader as fixtures
        from datetime import datetime
        fixture=fixtures.AnkiTests();fixture.setUp()
        try:
            fixture.db.execute('UPDATE config SET val=? WHERE key=?',(str((datetime.now().hour+1)%24),'rollover'))
            fixture.db.execute('DELETE FROM revlog')
            fixture.db.execute('INSERT INTO revlog(id,cid,ease,type) VALUES(?,?,3,1)',(int((time.time()-3600)*1000),1));fixture.db.commit();fixture.exclusive()
            tools=self.pet.study_tools;tools.anki_enabled=True;tools.anki_path=str(fixture.path)
            tools.refresh_anki(force=True);directory=Path(tools.anki_process.scratch.name)
            self.wait_until(lambda:tools.anki_process is None,10)
            self.assertEqual(tools.anki_cards[0]['front'],'学习')
            self.assertIn('1 carta',tools.anki_status);self.assertFalse(directory.exists())
            self.assertFalse(tools.anki_timeout.isActive())
        finally:fixture.tearDown()

    def test_anki_failed_launch_cleans_up_without_later_timeout(self):
        tools=self.pet.study_tools;tools.anki_enabled=True;tools.anki_path=str(Path(self.tmp.name)/'collection.anki2')
        with patch.object(tools,'worker_python',return_value=str(Path(self.tmp.name)/'missing-python')):
            tools.refresh_anki(force=True);self.wait_until(lambda:tools.anki_process is None)
        self.assertFalse(tools.anki_timeout.isActive());self.assertIn('non riuscita',tools.anki_status)

    def test_anki_repeated_manual_practice_rotates_and_suspended_option_invalidates_cache(self):
        tools=self.pet.study_tools;tools.anki_enabled=True;tools.anki_valid_until=time.time()+600
        tools.anki_cards=[dict(id=i,note_id=i,front=str(i),back='Risposta',front_paths=[],back_paths=[]) for i in range(6)]
        tools.open_anki();dialog=tools.active_dialog;self.assertEqual(dialog.row['id'],0);dialog.close();app.processEvents()
        tools.open_anki();dialog=tools.active_dialog;self.assertEqual(dialog.row['id'],3)
        with patch.object(tools,'refresh_anki') as refresh:
            settings=StudySettings(self.pet);settings.suspended.setChecked(True)
            self.assertTrue(self.store.preference('study_anki_suspended',False))
            self.assertTrue(tools.anki_include_suspended);self.assertEqual(tools.anki_cards,[])
            self.assertIsNone(tools.active_dialog);refresh.assert_called_once_with(force=True)
            settings.deleteLater()

    def test_unreadable_models_are_not_reported_as_absent_difficult_cards(self):
        tools=self.pet.study_tools;process=Mock();process.scratch=tempfile.TemporaryDirectory()
        process.readAllStandardOutput.return_value=json.dumps(dict(cards=[],unsupported=1,issues=['Filtro non supportato.'],
            checked=time.time(),study_start=time.time()-3600,study_end=time.time()+3600)).encode()
        tools.anki_process=process;tools.anki_finished(process,0)
        self.assertIn('modello non supportato',tools.anki_status)
        self.assertNotIn('Nessuna carta difficile',tools.anki_status)
        self.assertEqual(tools.anki_detail,'Filtro non supportato.')

    def anki_result(self,tools,cards,**extra):
        now=time.time();process=Mock();process.scratch=tempfile.TemporaryDirectory()
        process.readAllStandardOutput.return_value=json.dumps(dict(cards=cards,checked=now,
            study_start=tools.anki_day or now-3600,study_end=now+3600,**extra)).encode()
        tools.anki_process=process;tools.anki_finished(process,0)

    def test_anki_status_counts_the_whole_selection_and_empty_page_can_restart(self):
        tools=self.pet.study_tools;tools.anki_enabled=True
        cards=[dict(id=i,note_id=i,front=str(i),back='Risposta',front_paths=[],back_paths=[]) for i in range(36)]
        self.anki_result(tools,cards,total=580,more=True)
        self.assertEqual(tools.anki_status,'580 carte selezionate');self.assertEqual(len(tools.anki_cards),36)
        self.anki_result(tools,[],total=580,more=False)
        settings=StudySettings(self.pet)
        self.assertTrue(settings.practice_button.isEnabled());settings.deleteLater()

    def test_anki_next_page_and_later_refresh_preserve_more_than_512_seen_notes(self):
        tools=self.pet.study_tools;tools.anki_enabled=True;tools.anki_day=time.time()-3600
        tools.anki_seen=list(range(600));tools.anki_path=str(Path(self.tmp.name)/'collection.anki2')
        tools.anki_cards=[];tools.anki_more=True;tools.anki_valid_until=time.time()+600
        with patch.object(tools,'refresh_anki') as refresh:
            tools.open_anki();refresh.assert_called_once_with(force=True)
        self.assertTrue(tools.anki_requested);self.assertEqual(tools.anki_seen,list(range(600)))
        cards=[dict(id=i,note_id=i,front=str(i),back='Risposta',front_paths=[],back_paths=[]) for i in range(600,606)]
        self.anki_result(tools,cards,total=900,more=True)
        self.assertEqual(tools.active_dialog.row['id'],600)
        self.assertEqual(tools.anki_seen,list(range(603)));tools.active_dialog.close();app.processEvents()
        # A refreshed page is already filtered by the worker. It must not cause
        # the controller to forget notes from earlier pages in the same day.
        self.anki_result(tools,cards[3:],total=900,more=True)
        tools.open_anki();self.assertEqual(tools.active_dialog.row['id'],603)
        self.assertEqual(tools.anki_seen,list(range(606)))

    def test_anki_restart_response_resets_seen_notes_once(self):
        tools=self.pet.study_tools;tools.anki_enabled=True;tools.anki_day=time.time()-3600
        tools.anki_seen=[1,2,3];tools.anki_requested=True
        cards=[dict(id=i,note_id=i,front=str(i),back='Risposta',front_paths=[],back_paths=[]) for i in (1,2,3)]
        self.anki_result(tools,cards,total=3,more=False,restarted=True)
        self.assertEqual(tools.anki_seen,[1,2,3]);self.assertEqual(tools.active_dialog.row['id'],1)

    def test_anki_worker_pages_past_512_with_a_large_history_request(self):
        import test_anki_reader as fixtures
        from yun_jin_anki import study_window
        from datetime import datetime
        fixture=fixtures.AnkiTests();fixture.setUp()
        try:
            fixture.now=time.time();fixture.large_collection(count=6000)
            fixture.db.execute('UPDATE config SET val=? WHERE key=?',(str((datetime.now().hour+1)%24),'rollover'))
            fixture.db.commit()
            tools=self.pet.study_tools;tools.anki_enabled=True;tools.anki_path=str(fixture.path)
            tools.anki_day=study_window(fixture.db,fixture.now)[0]
            tools.anki_seen=list(range(5481,6001))+list(range(1700000000000,1700000001000))
            self.assertGreater(len(json.dumps(tools.anki_seen)),16384)
            tools.anki_requested=True;tools.refresh_anki(force=True)
            self.wait_until(lambda:tools.anki_process is None,10)
            self.assertEqual(tools.anki_total,600);self.assertEqual(len(tools.anki_cards),36)
            self.assertEqual(tools.active_dialog.row['id'],5480)
            self.assertEqual(len(tools.anki_seen),1523)
        finally:fixture.tearDown()

    def test_single_anki_profile_is_selected_without_enabling_access(self):
        profile=Path(self.tmp.name)/'Utente 1'/'collection.anki2';profile.parent.mkdir();profile.touch()
        tools=self.pet.study_tools
        with patch('yun_jin_anki.find_profiles',return_value=[profile]),patch.object(tools,'refresh_anki') as refresh:
            dialog=StudySettings(self.pet)
            self.assertEqual(dialog.profiles.currentData(),str(profile));self.assertEqual(tools.anki_path,str(profile))
            self.assertFalse(tools.anki_enabled);refresh.assert_not_called()
            dialog.anki.setChecked(True);refresh.assert_called_once_with(force=True)
            with patch('yun_jin_study_ui.choose_files',return_value=[]) as choose:
                dialog.browse()
                self.assertEqual(choose.call_args.kwargs['directory'],profile.parent)
                self.assertEqual(choose.call_args.kwargs['filename'],'collection.anki2')
            dialog.deleteLater()

    def test_multiple_anki_profiles_require_a_choice(self):
        profiles=[Path(self.tmp.name)/name/'collection.anki2' for name in ('Utente 1','Utente 2')]
        with patch('yun_jin_anki.find_profiles',return_value=profiles):
            dialog=StudySettings(self.pet)
            self.assertEqual(dialog.profiles.currentData(),'');self.assertFalse(self.pet.study_tools.anki_path)
            dialog.deleteLater()

    def test_quick_review_respects_daily_limit_changed_after_prompt(self):
        cid=self.make_hard();candidates=[self.s.card(cid)]
        options=self.s.deck(self.deck)['settings'];options['review_limit']=0
        self.s.save_deck('Cinese',options,self.deck)
        self.pet.study_tools.open_review(quick_cards=candidates)
        self.assertTrue(self.pet.study_tools.active_dialog.finished_session)
        self.assertEqual(self.s.card(cid)['reps'],1)

    def test_optimizer_subprocess_finishes_without_blocking_gui(self):
        cid=self.add();sid=self.s.start_session(self.deck);self.s.review(cid,3,sid);self.s.end_session(sid)
        tools=self.pet.study_tools;tools.optimize([self.deck]);tools.fit_delay.stop();tools.start_fit()
        ticks=[];timer=QTimer();timer.timeout.connect(lambda:ticks.append(1));timer.start(10)
        self.wait_until(lambda:tools.fit_process is None);timer.stop()
        self.assertGreater(len(ticks),0);self.assertEqual(self.s.deck(self.deck)['optimizer_status'],'waiting')
        self.assertIsNone(self.s.deck(self.deck)['parameters'])

    def test_images_change_between_cards_and_documents_do_not_accumulate(self):
        from PyQt6.QtGui import QImage,QColor,QTextDocument
        from PyQt6.QtCore import QUrl,QEvent
        from yun_jin_study_widgets import CardFace,CardDocument
        face=CardFace(self.pet);face.show()
        for index,color in enumerate(('red','blue','green')):
            path=Path(self.tmp.name)/f'{index}.png';image=QImage(24,24,QImage.Format.Format_ARGB32);image.fill(QColor(color));image.save(str(path))
            media=self.s.import_media(path)
            face.present(dict(kind='basic',ordinal=0,content=dict(front='Immagine',back='Retro',front_media=[media],back_media=[])))
            app.processEvents();app.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            resource=face.browser.document().resource(QTextDocument.ResourceType.ImageResource,QUrl('yjmedia:/0'))
            self.assertEqual(resource.pixelColor(0,0).name(),QColor(color).name())
            self.assertLessEqual(len(face.browser.findChildren(CardDocument)),1)
        face.close();face.deleteLater()

    def test_card_audio_respects_mute_quiet_time_and_zero_volume(self):
        from yun_jin_study_widgets import CardFace
        face=CardFace(self.pet);face.player=Mock();face.output=Mock()
        path=Path(self.tmp.name)/'voce.wav'
        self.pet.sound.enabled=False;face.play(path);face.player.play.assert_not_called()
        self.pet.sound.enabled=True;self.pet.sound.quiet_until=time.time()+60
        face.play(path);face.player.play.assert_not_called()
        self.pet.sound.quiet_until=0;self.pet.sound.volume=0
        face.play(path);face.output.setVolume.assert_called_with(0)
        self.pet.sound.volume=.37;face.play(path);face.output.setVolume.assert_called_with(.37)
        self.assertEqual(face.player.play.call_count,2);face.deleteLater()

    def test_no_heavy_optimizer_import_or_fast_background_clock_in_gui(self):
        self.assertNotIn('fsrs_rs_python',sys.modules);self.assertNotIn('torch',sys.modules)
        self.assertEqual(self.pet.study_tools.timer.interval(),60000)
        self.assertEqual(self.pet.study_tools.timer.timerType(),Qt.TimerType.VeryCoarseTimer)
        self.pet.study_tools.set_enabled(False);self.assertFalse(self.pet.study_tools.timer.isActive())

    def test_new_review_and_editor_windows_follow_mac_overlay_layers(self):
        self.add()
        levels={};native=SimpleNamespace(set_accessory=Mock(),snapshot=lambda w:(int(w.winId()),0,0),
            configure=lambda w,level:levels.__setitem__(w,level),restore=Mock(),focus=Mock())
        controller=MacOverlay(app,self.pet,native);self.pet.mac_overlay=controller
        controller.set_enabled(True)
        self.pet.open_panel(tab=6);app.processEvents()
        try:
            dialog=self.open();controller.apply(dialog)
            self.assertIs(dialog.parentWidget(),self.pet.panel)
            self.assertGreater(levels[dialog],levels[self.pet.panel]);native.focus.assert_any_call(dialog)
            editor=NoteEditor(self.pet,self.deck,parent=dialog);controller.prepare(editor);editor.show();controller.apply(editor)
            self.assertGreater(levels[editor],levels[dialog]);editor.close();editor.deleteLater()
        finally:
            controller.set_enabled(False);app.removeEventFilter(controller);self.pet.mac_overlay=None;controller.deleteLater()


if __name__=='__main__':unittest.main(verbosity=2)
