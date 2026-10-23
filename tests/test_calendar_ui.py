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
from PyQt6.QtWidgets import QApplication,QWidget,QDialog,QScrollArea,QVBoxLayout,QMessageBox,QLabel,QBoxLayout
from yun_jin_data import Store
from yun_jin_agenda import AgendaStore
from yun_jin_calendar_ui import (CalendarPanel,CalendarHero,EventDialog,RecurrenceEditor,
                                ScopeDialog,MonthJumpDialog,IllustrationDialog,CalendarBackdrop,DayButton,parse_local,exec_editor)
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
        hero=self.keep(CalendarHero());module=SimpleNamespace(illustration_for=lambda y,m,d=1:files[m-1])
        with patch.dict(sys.modules,{'yun_jin_calendar_art':module}):
            for month in (1,2,3):hero.set_month(date(2032,month,1))
        self.assertEqual(len(hero.cache),2);self.assertNotIn(files[0],hero.cache)
        self.assertAlmostEqual(hero.pixmap.width()/hero.pixmap.height(),1.5,places=2)
        self.assertLessEqual(hero.pixmap.width(),1000);self.assertLessEqual(hero.pixmap.height(),600)
        with patch.dict(sys.modules,{'yun_jin_calendar_art':SimpleNamespace(illustration_for=lambda y,m,d=1:Path(self.tmp.name)/'missing.webp')}):
            hero.set_month(date(2032,4,1));self.assertIsNone(hero.pixmap)

    def test_daily_selection_mouse_keyboard_preview_and_cache(self):
        files=[]
        for i,color in enumerate(('#ff0000','#00ff00','#0000ff')):
            path=Path(self.tmp.name)/f'daily-{i}.png';image=QImage(900,600,QImage.Format.Format_RGB32)
            image.fill(QColor(color));image.save(str(path));files.append(path)
        module=SimpleNamespace(illustration_for=lambda y,m,d:files[(d-1)%3])
        with patch.dict(sys.modules,{'yun_jin_calendar_art':module}):
            page=self.keep(CalendarPanel(self.pet));page.select_day(date(2060,10,1));page.show();app.processEvents()
            self.assertEqual(page.hero.path,files[0])
            cell=next(b for b in page.days if b.day==date(2060,10,2));QTest.mouseClick(cell,Qt.MouseButton.LeftButton)
            self.assertEqual(page.selected,date(2060,10,2));self.assertEqual(page.hero.path,files[1])
            QTest.keyClick(cell,Qt.Key.Key_Right);self.assertEqual(page.hero.path,files[2]);self.assertEqual(page.hero.day,date(2060,10,3))
            self.assertEqual(len(page.hero.cache),2);self.assertIs(page.month_box.hero.pixmap,page.hero.pixmap)
            with patch('yun_jin_calendar_ui.QImageReader',side_effect=AssertionError('Same-day refresh must reuse pixels')):
                page.refresh();page.select_day(date(2060,10,2))
            def inspect(dialog,pet):
                self.assertIn('2 ottobre 2060',dialog.windowTitle());self.assertFalse(dialog.canvas.pixmap.isNull());return QDialog.DialogCode.Rejected
            with patch('yun_jin_calendar_ui.exec_dialog',side_effect=inspect):page.preview_illustration(page.hero.path)
            self.assertEqual(page.findChildren(QTimer),[])

    def test_midnight_follows_today_but_preserves_browsing_and_updates_on_reopen(self):
        class ClockDate(date):
            current=date(2060,10,30)
            @classmethod
            def today(cls):return cls.current
        with patch('yun_jin_calendar_ui.date',ClockDate):
            page=self.keep(CalendarPanel(self.pet));page.show();app.processEvents()
            ClockDate.current=date(2060,10,31);self.pet.agenda_changed.emit()
            self.assertEqual(page.selected,ClockDate.current);self.assertEqual(page.hero.day,ClockDate.current)
            page.select_day(date(2050,10,5));ClockDate.current=date(2060,11,1);self.pet.agenda_changed.emit()
            self.assertEqual(page.selected,date(2050,10,5))
            page.today();page.hide();ClockDate.current=date(2060,11,2);self.pet.agenda_changed.emit()
            self.assertEqual(page.selected,date(2060,11,1))
            page.show();app.processEvents();self.assertEqual(page.selected,ClockDate.current)
            self.assertEqual(page.hero.day,ClockDate.current);self.assertEqual(page.findChildren(QTimer),[])

    def test_real_daily_art_changes_at_midnight_month_year_and_leap_boundaries(self):
        from yun_jin_calendar_art import illustration_for
        class ClockDate(date):
            current = date(2031, 12, 30)
            @classmethod
            def today(cls): return cls.current
        with patch('yun_jin_calendar_ui.date', ClockDate):
            page = self.keep(CalendarPanel(self.pet)); page.show(); app.processEvents()
            previous_path = page.hero.path
            for day in (date(2031, 12, 31), date(2032, 1, 1), date(2032, 1, 2),
                        date(2032, 2, 28), date(2032, 2, 29), date(2032, 3, 1),
                        date(2032, 3, 2), date(2032, 3, 31), date(2032, 4, 1),
                        date(2032, 4, 30), date(2032, 5, 1), date(2032, 5, 31)):
                ClockDate.current = day; self.pet.agenda_changed.emit(); app.processEvents()
                self.assertEqual(page.selected, day)
                self.assertEqual(page.hero.path, illustration_for(day.year, day.month, day.day))
                self.assertNotEqual(page.hero.path, previous_path)
                self.assertFalse(page.hero.pixmap.isNull())
                self.assertLessEqual(len(page.hero.cache), 2)
                previous_path = page.hero.path
            page.select_day(date(2032, 2, 15))
            ClockDate.current = date(2032, 3, 2); self.pet.agenda_changed.emit()
            self.assertEqual(page.selected, date(2032, 2, 15))
            self.assertEqual(page.findChildren(QTimer), [])

    def test_calendar_background_reuses_pixels_through_resize_month_changes_and_close(self):
        files={}
        for month,color in [(1,'#ff0000'),(2,'#0000ff'),(3,'#ffffff')]:
            path=Path(self.tmp.name)/f'background-{month}.png'
            image=QImage(1200,800,QImage.Format.Format_RGB32);image.fill(QColor(color));image.save(str(path));files[month]=path
        module=SimpleNamespace(illustration_for=lambda y,m,d=1:files.get(m,files[1]))
        with patch.dict(sys.modules,{'yun_jin_calendar_art':module}):
            page=self.keep(CalendarPanel(self.pet));page.setStyleSheet(STYLE);page.select_day(date(2032,1,15));page.show();app.processEvents()
            initial=page.hero.pixmap.cacheKey()
            with patch('yun_jin_calendar_ui.QImageReader',side_effect=AssertionError('Resizing must reuse decoded artwork')):
                for width,height in [(800,650),(520,560),(1100,760),(540,600)]:
                    page.resize(width,height)
                    for _ in range(4):app.processEvents()
                    shot=page.month_box.grab().toImage()
                    self.assertFalse(shot.isNull());self.assertEqual(page.hero.pixmap.cacheKey(),initial)
                    source=page.month_box.image_source_rect()
                    self.assertAlmostEqual(source.width()/source.height(),page.month_box.width()/page.month_box.height())
                    self.assertGreaterEqual(source.left(),0);self.assertGreaterEqual(source.top(),0)
                    self.assertLessEqual(source.right(),page.hero.pixmap.width());self.assertLessEqual(source.bottom(),page.hero.pixmap.height())
                    self.assertEqual(page.middle_layout.direction(),QBoxLayout.Direction.LeftToRight if width>=680 else QBoxLayout.Direction.TopToBottom)
                    scroll=page.findChild(QScrollArea);self.assertEqual(scroll.horizontalScrollBar().maximum(),0)
                before=page.month_box.grab().toImage()
            page.change_month(1);app.processEvents();after=page.month_box.grab().toImage()
            self.assertNotEqual(before,after);self.assertNotEqual(page.hero.pixmap.cacheKey(),initial)
            page.change_month(1);app.processEvents();self.assertEqual(len(page.hero.cache),2)
            self.assertNotIn(files[1],page.hero.cache);self.assertEqual(page.month_box.hero.pixmap.cacheKey(),page.hero.pixmap.cacheKey())
            with patch('yun_jin_calendar_ui.QImageReader',side_effect=AssertionError('Closing must not decode artwork')):page.close();app.processEvents()
            self.assertFalse(page.isVisible());self.assertEqual(page.findChildren(QTimer),[])

    def test_calendar_background_keeps_bright_art_subdued_and_day_states_distinct(self):
        path=Path(self.tmp.name)/'white-scene.png';image=QImage(900,600,QImage.Format.Format_RGB32)
        image.fill(QColor('#ffffff'));image.save(str(path))
        hero=self.keep(CalendarHero())
        with patch.dict(sys.modules,{'yun_jin_calendar_art':SimpleNamespace(illustration_for=lambda y,m,d=1:path)}):hero.set_month(date(2032,1,1))
        surface=self.keep(CalendarBackdrop(hero));surface.resize(630,350);surface.show();app.processEvents()
        background=surface.grab().toImage();ratio=background.devicePixelRatio()
        def luminance(value):
            channels=[value.redF(),value.greenF(),value.blueF()]
            linear=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in channels]
            return sum(x*weight for x,weight in zip(linear,(.2126,.7152,.0722)))
        for y in (30,170,320):
            color=background.pixelColor(round(300*ratio),round(y*ratio))
            self.assertLess(max(color.red(),color.green(),color.blue()),110)
            self.assertGreater((luminance(QColor('#eee6f3'))+.05)/(luminance(color)+.05),4.5)
            if y==30:self.assertGreater((luminance(QColor('#d0c8dc'))+.05)/(luminance(color)+.05),4.5)
        day=DayButton(date.today());day.setParent(surface);day.setGeometry(200,280,70,50);day.show()
        captures=[]
        for current,chosen,events in [(True,False,[]),(True,True,[]),(False,False,[]),(True,False,[{'title':'Prova','color':'teal'}])]:
            day.update_day(date.today(),current,chosen,events);day.is_today=current and not chosen;day.update();app.processEvents()
            captures.append(day.grab().toImage())
        for index,shot in enumerate(captures):
            for other in captures[index+1:]:self.assertNotEqual(shot,other)
        self.assertIn('1 impegni',day.accessibleName());self.assertIn('Prova',day.toolTip())
        future=date.today()+timedelta(days=5)
        day.update_day(future,True,False,[]);app.processEvents();plain=day.grab().toImage()
        day.update_day(future,True,True,[]);app.processEvents();self.assertNotEqual(day.grab().toImage(),plain)
        day.update_day(future,True,False,[]);app.processEvents();self.assertEqual(day.grab().toImage(),plain)
        day.update_day(future,False,False,[]);app.processEvents()
        muted_background=surface.grab().toImage().pixelColor(round(210*ratio),round(290*ratio))
        self.assertGreater((luminance(QColor('#bfb3ca'))+.05)/(luminance(muted_background)+.05),4.5)
        with patch.dict(sys.modules,{'yun_jin_calendar_art':SimpleNamespace(illustration_for=lambda y,m,d=1:Path(self.tmp.name)/'missing.webp')}):hero.set_month(date(2032,2,1))
        surface.update();app.processEvents();cleared=surface.grab().toImage()
        self.assertIsNone(hero.pixmap);self.assertNotEqual(cleared,background)
        self.assertEqual(cleared.pixelColor(round(300*ratio),round(30*ratio)),QColor('#252131'))

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
        module=SimpleNamespace(illustration_for=lambda y,m,d=1:path)
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

    def test_illustration_mouse_close_without_titlebar_preserves_owner_and_releases_pixels(self):
        from yun_jin_dialogs import exec_dialog
        path=Path(self.tmp.name)/'scene.png';image=QImage(800,500,QImage.Format.Format_RGB32)
        image.fill(QColor('#30404f'));image.save(str(path))
        owner=self.keep(QWidget());owner.show();self.pet.show();app.processEvents()
        for dismiss in ('mouse','escape'):
            with self.subTest(dismiss=dismiss):
                dialog=self.keep(IllustrationDialog(self.pet,owner,path,date(2032,2,1)))
                # macOS overlay panels cannot be assumed to provide native
                # title-bar controls. The in-content close button must suffice.
                dialog.setWindowFlag(Qt.WindowType.FramelessWindowHint,True)
                errors=[];driver=QTimer();driver.setInterval(5)
                timeout=QTimer();timeout.setSingleShot(True)
                def expire():
                    errors.append(AssertionError('Illustration dialog did not close'));dialog.reject()
                def inspect():
                    if app.activeModalWidget() is not dialog:return
                    driver.stop()
                    try:
                        close=dialog.close_button
                        self.assertTrue(close.isVisible());self.assertTrue(close.isEnabled())
                        self.assertEqual(close.accessibleName(),'Chiudi');self.assertEqual(close.toolTip(),'Chiudi')
                        self.assertFalse(close.icon().isNull());self.assertEqual(close.text(),'')
                        self.assertFalse(close.geometry().intersects(dialog.canvas.geometry()))
                        self.assertAlmostEqual(dialog.canvas.image_rect().width()/dialog.canvas.image_rect().height(),1.6)
                        if dismiss=='mouse':QTest.mouseClick(close,Qt.MouseButton.LeftButton)
                        else:QTest.keyClick(dialog,Qt.Key.Key_Escape)
                    except Exception as exc:errors.append(exc);dialog.reject()
                driver.timeout.connect(inspect);timeout.timeout.connect(expire)
                with patch.object(self.pet,'focus_tool') as focus:
                    driver.start();timeout.start(3000)
                    try:result=exec_dialog(dialog,self.pet)
                    finally:driver.stop();timeout.stop()
                    if errors:raise errors[0]
                    self.assertEqual(result,QDialog.DialogCode.Rejected)
                    self.assertFalse(dialog.isVisible());self.assertTrue(dialog.canvas.pixmap.isNull())
                    self.assertTrue(owner.isVisible());self.assertTrue(owner.isEnabled());self.assertTrue(self.pet.isVisible())
                    focus.assert_any_call(owner)


if __name__=='__main__':unittest.main(verbosity=2)
