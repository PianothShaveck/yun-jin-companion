"""Calendar/alarm edits, recurrence scopes, keyboard access and bounded GUI resources."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import sys
import tempfile
import unittest
from datetime import date,datetime,timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from PyQt6 import sip
from PyQt6.QtCore import Qt,QDate,QTime,QTimer,QCoreApplication,QEvent,pyqtSignal
from PyQt6.QtGui import QImage,QColor,QPainter
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication,QWidget,QDialog,QScrollArea,QVBoxLayout,QMessageBox,QLabel
from yun_jin_data import Store
from yun_jin_agenda import AgendaStore
from yun_jin_calendar_ui import (CalendarPanel,CalendarHero,EventDialog,RecurrenceEditor,
                                ScopeDialog,MonthJumpDialog,IllustrationDialog,parse_local,exec_editor)
from yun_jin_alarms_ui import AlarmDialog,AlarmsPanel
from yun_jin_ui import STYLE

app=QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)


class Pet(QWidget):
    agenda_changed=pyqtSignal()
    def __init__(self,store):
        super().__init__();self.store=store;self.closing=False;self.refresh_count=0
        self.store.agenda
    def refresh_agenda(self):self.refresh_count+=1
    def focus_tool(self,widget):pass


class CalendarUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name);self.pet=Pet(self.store);self.widgets=[]
    def tearDown(self):
        for widget in reversed(self.widgets):widget.close();widget.deleteLater()
        self.pet.close();self.pet.deleteLater();app.processEvents();self.store.close();self.tmp.cleanup()
    def keep(self,widget):self.widgets.append(widget);return widget
    def event(self,**kwargs):
        defaults=dict(title='Prova orchestra',start='2032-02-28T10:00:00',end='2032-02-28T11:00:00')
        defaults.update(kwargs);return self.store.agenda.save_event(**defaults)
    def dialog(self,**kwargs):return self.keep(EventDialog(self.pet,day=date(2032,2,28),**kwargs))

    def test_event_editor_validates_before_write_and_cancel_does_not_save(self):
        dialog=self.dialog();dialog.save();self.assertIn('vuoto',dialog.error.text());self.assertEqual(self.store.agenda.events(),[])
        dialog.title.setText('中文 <b>prova</b>');dialog.start_time.setTime(QTime(15,0));dialog.end_time.setTime(QTime(14,0))
        dialog.save();self.assertIn('fine',dialog.error.text());self.assertEqual(self.store.agenda.events(),[])
        dialog.end_time.setTime(QTime(16,0));dialog.details.setPlainText('Nota <script>inert</script>');dialog.reject()
        self.assertEqual(self.store.agenda.events(),[])
        dialog=self.dialog();dialog.title.setText('中文 <b>prova</b>');dialog.save()
        self.assertEqual(dialog.result(),QDialog.DialogCode.Accepted);self.assertIsNotNone(dialog.saved_id)
        row=self.store.agenda.get(dialog.saved_id);self.assertEqual(row['title'],'中文 <b>prova</b>');self.assertEqual(self.pet.refresh_count,1)

    def test_all_day_editor_has_inclusive_end_but_stores_exclusive_boundary(self):
        dialog=self.dialog();dialog.title.setText('Viaggio');dialog.all_day.setChecked(True)
        dialog.start_date.setDate(QDate(2032,2,28));dialog.end_date.setDate(QDate(2032,3,1));dialog.save()
        row=self.store.agenda.get(dialog.saved_id)
        self.assertTrue(row['all_day']);self.assertEqual(parse_local(row['end_local']).date(),date(2032,3,2))
        reopened=self.dialog(event=row);self.assertEqual(reopened.end_date.date(),QDate(2032,3,1))
        page=self.keep(CalendarPanel(self.pet));page.select_day(date(2032,2,28))
        for day in (date(2032,2,28),date(2032,2,29),date(2032,3,1)):self.assertEqual(len(page.day_rows[day]),1)
        self.assertNotIn(date(2032,3,2),page.day_rows)

    def test_recurrence_fields_weekdays_count_until_and_none(self):
        editor=self.keep(RecurrenceEditor(date(2032,2,28)))
        self.assertIsNone(editor.value());editor.frequency.setCurrentIndex(editor.frequency.findData('weekly'));editor.days.set_selected([])
        with self.assertRaisesRegex(ValueError,'almeno un giorno'):editor.value()
        editor.days.set_selected([0,2,4]);editor.interval.setValue(2);editor.end_mode.setCurrentIndex(2);editor.count.setValue(9)
        self.assertEqual(editor.value(),dict(frequency='weekly',interval=2,weekdays=[0,2,4],count=9))
        editor.end_mode.setCurrentIndex(1);editor.until.setDate(QDate(2032,6,1));rule=editor.value()
        self.assertEqual(rule['until'],'2032-06-01');self.assertNotIn('count',rule)
        dialog=self.dialog();dialog.title.setText('Prova');dialog.recurrence.frequency.setCurrentIndex(1)
        dialog.recurrence.end_mode.setCurrentIndex(1);dialog.recurrence.until.setDate(QDate(2032,2,1));dialog.save()
        self.assertIn('prima dell’inizio',dialog.error.text());self.assertEqual(self.store.agenda.events(),[])

    def test_single_occurrence_edit_and_delete_do_not_change_the_series(self):
        ident=self.event(recurrence={'frequency':'daily','count':3});event=self.store.agenda.get(ident)
        rows=self.store.agenda.occurrences('2032-02-28','2032-03-03');self.assertEqual(len(rows),3)
        dialog=self.dialog(event=event,occurrence=rows[1],scope='occurrence');dialog.title.setText('Solo questa prova')
        dialog.start_time.setTime(QTime(14,0));dialog.end_time.setTime(QTime(15,0));dialog.save()
        updated=self.store.agenda.occurrences('2032-02-28','2032-03-03')
        self.assertEqual([r['title'] for r in updated],['Prova orchestra','Solo questa prova','Prova orchestra'])
        self.assertEqual(self.store.agenda.get(ident)['start_local'],'2032-02-28T10:00:00')
        page=self.keep(CalendarPanel(self.pet));page.select_day(date(2032,2,29))
        with patch.object(page,'scope',return_value='occurrence'):page.delete_event(updated[1])
        self.assertEqual(len(self.store.agenda.occurrences('2032-02-28','2032-03-03')),2)
        self.assertIsNotNone(self.store.agenda.get(ident))

    def test_series_edit_preserves_single_exception_when_schedule_unchanged(self):
        ident=self.event(recurrence={'frequency':'daily','count':3})
        self.store.agenda.save_exception(ident,'2032-02-29T10:00:00',title='Eccezione')
        dialog=self.dialog(event=self.store.agenda.get(ident));dialog.title.setText('Nuovo titolo serie');dialog.save()
        rows=self.store.agenda.occurrences('2032-02-28','2032-03-03')
        self.assertEqual([r['title'] for r in rows],['Nuovo titolo serie','Eccezione','Nuovo titolo serie'])

    def test_calendar_keyboard_moves_across_month_and_enter_creates_on_selected_day(self):
        page=self.keep(CalendarPanel(self.pet));page.select_day(date(2032,2,29),focus=True);page.show();app.processEvents()
        cell=next(b for b in page.days if b.day==date(2032,2,29))
        QTest.keyClick(cell,Qt.Key.Key_Right);self.assertEqual(page.selected,date(2032,3,1));self.assertEqual(page.month,date(2032,3,1))
        cell=next(b for b in page.days if b.day==date(2032,3,1))
        with patch.object(page,'new_event') as create:QTest.keyClick(cell,Qt.Key.Key_Return);create.assert_called_once_with(date(2032,3,1))
        self.assertEqual(len(page.days),42);self.assertEqual(page.days[0].day.weekday(),0)

    def test_event_labels_are_plain_and_long_titles_do_not_expand_small_panel(self):
        self.event(title='<b>'+('中文 title '*17)+'</b>',details='<img src=x>')
        host=self.keep(QWidget());host.setStyleSheet(STYLE);layout=QVBoxLayout(host);page=CalendarPanel(self.pet);layout.addWidget(page)
        page.select_day(date(2032,2,28));host.resize(530,510);host.show()
        for _ in range(4):app.processEvents()
        self.assertLessEqual(host.width(),530);self.assertTrue(all(b.height()>=39 for b in page.days))
        scroll=page.findChild(QScrollArea);self.assertEqual(scroll.horizontalScrollBar().maximum(),0)
        self.assertGreater(scroll.verticalScrollBar().maximum(),0)
        labels=page.events_widget.findChildren(QLabel)
        self.assertTrue(all(l.textFormat()==Qt.TextFormat.PlainText for l in labels))
        page.hide();self.assertEqual(page.findChildren(QTimer),[])

    def test_illustrations_are_lazy_bounded_and_keep_original_aspect(self):
        files=[]
        for i in range(3):
            path=Path(self.tmp.name)/f'art-{i}.png';image=QImage(1200,800,QImage.Format.Format_RGB32);image.fill(QColor('#765380'));image.save(str(path));files.append(path)
        hero=self.keep(CalendarHero());module=SimpleNamespace(illustration_for=lambda y,m:files[m-1])
        with patch.dict(sys.modules,{'yun_jin_calendar_art':module}):
            for month in (1,2,3):hero.set_month(date(2032,month,1))
        self.assertEqual(len(hero.cache),2);self.assertNotIn(files[0],hero.cache)
        self.assertAlmostEqual(hero.pixmap.width()/hero.pixmap.height(),1.5,places=2)
        self.assertLessEqual(hero.pixmap.width(),1000);self.assertLessEqual(hero.pixmap.height(),600)
        with patch.dict(sys.modules,{'yun_jin_calendar_art':SimpleNamespace(illustration_for=lambda y,m:Path(self.tmp.name)/'missing.webp')}):
            hero.set_month(date(2032,4,1));self.assertIsNone(hero.pixmap)

    def test_alarm_recurrence_voice_sound_and_disabled_state_survive_edit(self):
        dialog=self.keep(AlarmDialog(self.pet));dialog.title.setText('Lezione');dialog.clock.setTime(QTime(7,45))
        dialog.repeat.setCurrentIndex(dialog.repeat.findData('custom'));dialog.days.set_selected([]);dialog.save()
        self.assertIn('almeno un giorno',dialog.error.text());self.assertEqual(self.store.agenda.alarms(),[])
        dialog.days.set_selected([0,3]);dialog.snooze.setValue(7);dialog.voice.setChecked(False);dialog.sound.setChecked(True);dialog.save()
        row=self.store.agenda.get(dialog.saved_id);self.assertEqual(row['clock'],'07:45');self.assertEqual(row['weekdays'],[0,3])
        self.assertFalse(row['voice']);self.assertTrue(row['sound']);self.assertEqual(row['snooze_minutes'],7)
        page=self.keep(AlarmsPanel(self.pet));page.toggle_alarm(row['id'],False);self.assertFalse(self.store.agenda.get(row['id'])['enabled'])
        editor=self.keep(AlarmDialog(self.pet,alarm=self.store.agenda.get(row['id'])));editor.title.setText('Lezione aggiornata');editor.save()
        self.assertFalse(self.store.agenda.get(row['id'])['enabled']);self.assertEqual(editor.repeat.currentData(),'custom')

    def test_alarm_oneoff_date_and_daily_modes_are_distinct_and_cancel_is_inert(self):
        dialog=self.keep(AlarmDialog(self.pet));self.assertIsNone(dialog.payload()['on_date']);self.assertIsNone(dialog.payload()['weekdays'])
        dialog.repeat.setCurrentIndex(dialog.repeat.findData('date'));dialog.on_date.setDate(QDate(2032,5,3))
        self.assertEqual(dialog.payload()['on_date'],'2032-05-03');self.assertIsNone(dialog.payload()['weekdays'])
        dialog.repeat.setCurrentIndex(dialog.repeat.findData('daily'));self.assertEqual(dialog.payload()['weekdays'],list(range(7)));self.assertIsNone(dialog.payload()['on_date'])
        dialog.reject();self.assertEqual(self.store.agenda.alarms(),[])
        page=self.keep(AlarmsPanel(self.pet));self.assertEqual(page.findChildren(QTimer),[])

    def test_delete_confirmation_cancellation_keeps_event_and_alarm(self):
        ident=self.event();alarm=self.store.agenda.save_alarm('Mattina','08:00',weekdays=list(range(7)))
        page=self.keep(CalendarPanel(self.pet));page.select_day(date(2032,2,28));alarms=self.keep(AlarmsPanel(self.pet))
        with patch('yun_jin_calendar_ui.Messages.question',return_value=QMessageBox.StandardButton.No):
            page.delete_event(page.day_rows[date(2032,2,28)][0]);alarms.delete_alarm(self.store.agenda.get(alarm))
        self.assertIsNotNone(self.store.agenda.get(ident));self.assertIsNotNone(self.store.agenda.get(alarm))
        with patch('yun_jin_calendar_ui.Messages.question',return_value=QMessageBox.StandardButton.Yes):
            page.delete_event(page.day_rows[date(2032,2,28)][0]);alarms.delete_alarm(self.store.agenda.get(alarm))
        self.assertIsNone(self.store.agenda.get(ident));self.assertIsNone(self.store.agenda.get(alarm))

    def test_start_changes_preserve_duration_and_all_day_does_not_surprise_at_midnight(self):
        dialog=self.dialog();dialog.start_time.setTime(QTime(10,0));dialog.end_time.setTime(QTime(11,30))
        dialog.start_date.setDate(QDate(2032,3,4));dialog.start_time.setTime(QTime(14,0))
        self.assertEqual(dialog.end_date.date(),QDate(2032,3,4));self.assertEqual(dialog.end_time.time(),QTime(15,30))
        self.assertEqual(dialog.reminder.currentData(),10)
        dialog.all_day.setChecked(True);self.assertIsNone(dialog.reminder.currentData())
        dialog.all_day.setChecked(False);self.assertEqual(dialog.reminder.currentData(),10)
        dialog.reminder.setCurrentIndex(dialog.reminder.findData(1440));dialog.reminder.activated.emit(dialog.reminder.currentIndex())
        dialog.all_day.setChecked(True);self.assertEqual(dialog.reminder.currentData(),1440)

    def test_missed_and_snoozed_history_can_be_dismissed_without_reopening_an_editor(self):
        from yun_jin_agenda import wall_timestamp
        before=wall_timestamp('2032-02-28T06:00:00');later=wall_timestamp('2032-02-28T12:00:00')
        alarm=self.store.agenda.save_alarm('Mattina','08:00',now=before)
        self.store.agenda.poll(later)
        page=self.keep(AlarmsPanel(self.pet));self.assertEqual(len(page.history.rows),1)
        row=page.history.rows[0];self.assertEqual(row['state'],'missed')
        page.history.toggle.click();self.assertTrue(page.history.toggle.isChecked())
        page.history.dismiss(row['id']);self.assertEqual(page.history.rows,[])
        self.assertFalse(page.history.isVisible());self.assertIsNotNone(self.store.agenda.get(alarm))

    def test_storage_failure_keeps_event_text_and_does_not_accept_dialog(self):
        import sqlite3
        dialog=self.dialog();dialog.title.setText('Da conservare')
        with patch.object(self.store.agenda,'save_event',side_effect=sqlite3.OperationalError('locked')),self.assertLogs(level='ERROR'):
            dialog.save()
        self.assertEqual(dialog.title.text(),'Da conservare');self.assertEqual(dialog.result(),QDialog.DialogCode.Rejected)
        self.assertEqual(dialog.error.text(),'Salvataggio non riuscito. Riprova.')

    def test_page_editor_shares_guard_with_global_shortcuts(self):
        active=self.dialog();active.title.setText('Testo ancora da salvare');self.pet.agenda_editor=active
        duplicate=AlarmDialog(self.pet)
        with patch('yun_jin_calendar_ui.show_dialog') as show:
            result=exec_editor(duplicate,self.pet)
        self.assertEqual(result,QDialog.DialogCode.Rejected);show.assert_called_once_with(active,self.pet)
        self.assertIs(self.pet.agenda_editor,active);self.assertEqual(active.title.text(),'Testo ancora da salvare')
        self.pet.agenda_editor=None
        accepted=self.dialog()
        with patch('yun_jin_calendar_ui.exec_dialog',return_value=QDialog.DialogCode.Accepted) as run:
            self.assertEqual(exec_editor(accepted,self.pet),QDialog.DialogCode.Accepted)
        run.assert_called_once_with(accepted,self.pet);self.assertIsNone(self.pet.agenda_editor)
        # exec_editor owns its dialog's deferred deletion.
        self.widgets.remove(accepted)

    def test_refresh_hides_old_rows_immediately_and_large_days_are_lazy(self):
        for i in range(35):self.event(title=f'Impegno {i:02d}')
        page=self.keep(CalendarPanel(self.pet));page.select_day(date(2032,2,28));page.show();app.processEvents()
        old=page.events_layout.itemAt(0).widget();self.assertTrue(old.isVisible())
        self.assertEqual(page.events_layout.count(),31)
        page.more_events();self.assertFalse(old.isVisible());self.assertEqual(page.events_layout.count(),35)
        QTest.qWait(50)
        self.assertTrue(all(page.events_layout.itemAt(i).widget().isVisible() for i in range(35)))
        self.assertTrue(all(page.events_layout.itemAt(i).widget().height()>50 for i in range(35)))
        page.select_day(date(2032,2,29));self.assertEqual(page.visible_event_limit,30)
        alarm=self.store.agenda.save_alarm('Mattina','08:00',weekdays=list(range(7)))
        alarms=self.keep(AlarmsPanel(self.pet));alarms.show();app.processEvents();old=alarms.cards[alarm]['frame']
        alarms.refresh();self.assertFalse(old.isVisible())
        QTest.qWait(50);self.assertTrue(alarms.cards[alarm]['frame'].isVisible());self.assertGreater(alarms.cards[alarm]['frame'].height(),80)

    def test_illustration_click_opens_full_scene_escape_releases_pixels_and_title_still_jumps(self):
        path=Path(self.tmp.name)/'full-scene.png';image=QImage(800,500,QImage.Format.Format_RGB32);image.fill(QColor('#224422'))
        painter=QPainter(image);painter.fillRect(0,0,800,10,QColor('#ff0000'));painter.fillRect(0,490,800,10,QColor('#0000ff'));painter.end();image.save(str(path))
        module=SimpleNamespace(illustration_for=lambda y,m:path)
        with patch.dict(sys.modules,{'yun_jin_calendar_art':module}):page=self.keep(CalendarPanel(self.pet))
        page.resize(720,600);page.show();app.processEvents()
        self.assertTrue(page.hero.open_art.isVisible());self.assertEqual(page.hero.open_art.toolTip(),'Apri illustrazione')
        self.assertEqual(page.findChildren(IllustrationDialog),[])
        old_cache=list(page.hero.cache);seen=[];errors=[];driver=QTimer();driver.setInterval(5)
        timeout=QTimer();timeout.setSingleShot(True)
        def expire():
            errors.append(AssertionError('Illustration dialog did not open'))
            active=app.activeModalWidget()
            if active:active.reject()
        timeout.timeout.connect(expire)
        def inspect():
            dialog=app.activeModalWidget()
            if not isinstance(dialog,IllustrationDialog):return
            driver.stop();seen.append(dialog)
            try:
                self.assertEqual(dialog.canvas.pixmap.size(),image.size())
                canvas=dialog.canvas;rect=canvas.image_rect();self.assertAlmostEqual(rect.width()/rect.height(),1.6)
                self.assertGreaterEqual(rect.left(),0);self.assertLessEqual(rect.right(),canvas.width())
                self.assertGreaterEqual(rect.top(),0);self.assertLessEqual(rect.bottom(),canvas.height())
                captured=canvas.grab().toImage();ratio=captured.devicePixelRatio()
                top=captured.pixelColor(round(rect.center().x()*ratio),round((rect.top()+3)*ratio))
                bottom=captured.pixelColor(round(rect.center().x()*ratio),round((rect.bottom()-3)*ratio))
                self.assertGreater(top.red(),220);self.assertLess(top.blue(),30)
                self.assertGreater(bottom.blue(),220);self.assertLess(bottom.red(),30)
            except Exception as exc:errors.append(exc)
            finally:QTest.keyClick(dialog,Qt.Key.Key_Escape)
        driver.timeout.connect(inspect);driver.start();timeout.start(3000)
        try:QTest.mouseClick(page.hero.open_art,Qt.MouseButton.LeftButton)
        finally:driver.stop();timeout.stop()
        if errors:raise errors[0]
        self.assertEqual(len(seen),1);self.assertTrue(seen[0].canvas.pixmap.isNull())
        self.assertEqual(list(page.hero.cache),old_cache)
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.assertTrue(sip.isdeleted(seen[0]))
        with patch('yun_jin_calendar_ui.exec_dialog',return_value=QDialog.DialogCode.Rejected) as run:
            QTest.mouseClick(page.month_button,Qt.MouseButton.LeftButton)
        self.assertIsInstance(run.call_args.args[0],MonthJumpDialog);self.assertIs(run.call_args.args[1],self.pet)

    def test_month_jump_keeps_full_year_range_and_scope_choices_are_explicit(self):
        dialog=self.keep(MonthJumpDialog(self.pet,None,date(2032,2,1)));dialog.year.setValue(2048);dialog.month.setCurrentIndex(11)
        self.assertEqual(dialog.value(),date(2048,12,1))
        scope=self.keep(ScopeDialog(self.pet,None));scope.choose('occurrence');self.assertEqual(scope.scope,'occurrence')
        self.assertEqual(scope.result(),QDialog.DialogCode.Accepted)


if __name__=='__main__':unittest.main(verbosity=2)
