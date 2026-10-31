"""Language choice, catalog contracts, real widgets and preservation of user text."""
import ast,json,os,sys,tempfile,unittest,subprocess
from pathlib import Path
from string import Formatter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication,QPushButton,QComboBox
from yun_jin_i18n import tr,set_language,choose_language,language
from yun_jin_data import Store
from tests.test_google_ui import Pet
from yun_jin_calendar_ui import EventDialog,RecurrenceEditor,MonthJumpDialog,local_day_label
from datetime import date
app=QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)
ROOT=Path(__file__).resolve().parents[1]
class LocalizationTests(unittest.TestCase):
    def tearDown(self):set_language('it')
    def test_unconfigured_process_and_invalid_code_default_to_english(self):
        env = dict(os.environ)
        env.pop('YUNJIN_LANGUAGE', None)
        code = 'import sys;sys.path.insert(0,sys.argv[1]);from yun_jin_i18n import language,tr;print(language());print(tr("Titolo"))'
        result = subprocess.check_output([sys.executable, '-c', code, str(ROOT/'app')], env=env, text=True)
        self.assertEqual(result.splitlines(), ['en', 'Title'])
        set_language('invalid')
        self.assertEqual(language(), 'en')

    def test_first_run_enter_uses_english_and_existing_italian_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory)
            default_names=[]
            def accept_default():
                modal=app.activeModalWidget()
                default_names.extend(b.text() for b in modal.findChildren(QPushButton) if b.isDefault())
                QTest.keyClick(modal, Qt.Key.Key_Return)
            QTimer.singleShot(0, accept_default)
            self.assertTrue(choose_language(store))
            self.assertEqual(default_names, ['English'])
            self.assertEqual(store.preference('ui_language',''), 'en')
            store.set_preference('ui_language','it')
            store.set_preference('tts_language','zh-CN')
            self.assertTrue(choose_language(store))
            self.assertEqual(language(), 'it')
            self.assertEqual(store.preference('tts_language',''), 'zh-CN')
            store.close()
    def test_catalogs_complete_with_matching_placeholders(self):
        catalogs=[json.loads((ROOT/'app/locales'/name).read_text()) for name in ('en.json','zh-CN.json')]
        self.assertEqual(set(catalogs[0]),set(catalogs[1]))
        self.assertGreater(len(catalogs[0]),890)
        def fields(text):return sorted((field,spec,conv) for _,field,spec,conv in Formatter().parse(text) if field is not None)
        for catalog in catalogs:
            for key,value in catalog.items():
                self.assertTrue(value.strip(),key)
                self.assertEqual(fields(key),fields(value),key)
        missing=[]
        for path in (ROOT/'app').glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='tr' and node.args and isinstance(node.args[0],ast.Constant):
                    key=node.args[0].value
                    if key not in catalogs[0]:missing.append((path.name,key))
        self.assertEqual(missing,[])
    def test_first_run_choice_persisted_without_touching_existing_speech(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory);store.set_preference('tts_language','en')
            def select():
                modal=app.activeModalWidget()
                for button in modal.findChildren(QPushButton):
                    if button.text()=='简体中文':button.click();return
                self.fail('Language button missing')
            QTimer.singleShot(0,select)
            self.assertTrue(choose_language(store))
            self.assertEqual(language(),'zh-CN');self.assertEqual(store.preference('ui_language',''),'zh-CN')
            self.assertEqual(store.preference('tts_language',''),'en')
            self.assertTrue(choose_language(store))
            store.close()
    def test_new_profile_speech_follows_first_language(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory)
            def select():
                next(b for b in app.activeModalWidget().findChildren(QPushButton) if b.text()=='English').click()
            QTimer.singleShot(0,select);choose_language(store)
            self.assertEqual(store.preference('tts_language',''),'en');store.close()
    def test_real_editors_translate_but_do_not_change_user_text(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory);pet=Pet(store)
            item=store.agenda.save_event('Nuovo','2032-02-28T10:00:00',details='Salva')
            for code,title,repeat in [('it','Modifica impegno','Ogni giorno'),('en','Edit event','Every day'),('zh-CN','编辑日程','每天')]:
                set_language(code)
                dialog=EventDialog(pet,event=store.agenda.get(item))
                self.assertEqual(dialog.windowTitle(),title)
                self.assertEqual(dialog.title.text(),'Nuovo');self.assertEqual(dialog.details.toPlainText(),'Salva')
                self.assertEqual(dialog.recurrence.frequency.itemText(1),repeat)
                self.assertEqual(dialog.title.placeholderText(),tr('Titolo'))
                dialog.close();dialog.deleteLater();app.processEvents()
            self.assertIn('星期',local_day_label(date(2032,2,28)))
            pet.deleteLater();app.processEvents();store.close()
    def test_formatting_and_child_process_language(self):
        set_language('en');self.assertEqual(tr('Ogni {v0} settimane',v0=3),'Every 3 weeks')
        set_language('zh-CN');self.assertEqual(tr('Ogni {v0} settimane',v0=3),'每 3 周')
        self.assertEqual(os.environ['YUNJIN_LANGUAGE'],'zh-CN')
if __name__=='__main__':unittest.main()
