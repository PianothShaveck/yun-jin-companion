"""Forecast units, local times, failure handling and lazy GUI/resource boundaries."""
import copy
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from urllib.parse import parse_qs,urlparse
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from PyQt6.QtCore import QTimeZone,QEventLoop,QTimer,QObject,QProcess,pyqtSignal
from PyQt6.QtWidgets import QApplication
from yun_jin_forecast import fetch_forecast,cache_valid,condition,HOURLY,DAILY,CURRENT
from yun_jin_app import Companion
from yun_jin_data import Store
from yun_jin_forecast_service import ForecastService
app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False)
CITY=dict(city='Reggio Calabria',region='Calabria',country='Italia',latitude=38.11047,longitude=15.66129)


def response(now=None):
    now=time.time() if now is None else now;start=int(now//86400)*86400
    h={'time':[start+i*3600 for i in range(168)]};d={'time':[start+i*86400 for i in range(7)]}
    for key in HOURLY:
        h[key]=[1 if key=='is_day' else 0 if key=='weather_code' else 20 for i in range(168)]
    h['rain']=[0]*168;h['snowfall']=[0]*168
    for key in DAILY:
        d[key]=[stamp+7*3600 if key=='sunrise' else stamp+18*3600 if key=='sunset' else 0 if key=='weather_code' else 20 for stamp in d['time']]
    c={k:h[k][int((now-start)//3600)] for k in CURRENT};c['time']=int(now//900)*900
    return dict(timezone='UTC',utc_offset_seconds=0,current=c,hourly=h,daily=d)


def forecast(now=None):
    now=time.time() if now is None else now
    return fetch_forecast(CITY,now,Mock(return_value=response(now)))


class ForecastDataTests(unittest.TestCase):
    def test_seven_days_explicit_units_best_match_and_no_city_no_request(self):
        now=time.time();get=Mock(return_value=response(now));data=fetch_forecast(CITY,now,get)
        self.assertTrue(cache_valid(data,CITY,now));self.assertEqual(len(data['hourly']),168)
        self.assertEqual(len(data['daily']),7)
        query=parse_qs(urlparse(get.call_args.args[0]).query)
        for key,value in dict(models='best_match',timezone='auto',forecast_days='7',timeformat='unixtime',
                              temperature_unit='celsius',wind_speed_unit='kmh',precipitation_unit='mm').items():
            self.assertEqual(query[key],[value])
        get.reset_mock();self.assertIsNone(fetch_forecast(None,now,get));get.assert_not_called()
        self.assertLess(len(json.dumps(data).encode()),96*1024)

    def test_missing_data_never_becomes_zero_sun_or_a_false_probability(self):
        now=time.time();raw=response(now);raw['hourly'].pop('precipitation_probability')
        raw['hourly']['temperature_2m'][0]=None;raw['current']['weather_code']=12345
        data=fetch_forecast(CITY,now,Mock(return_value=raw))
        self.assertIsNone(data['hourly'][0]['precipitation_probability'])
        self.assertIsNone(data['hourly'][0]['temperature_2m']);self.assertEqual(condition(data['current']),('Non disponibile',None))
        self.assertTrue(cache_valid(data,CITY,now))
        for code,day,key in [(0,1,'sun'),(0,0,'clear_night'),(2,1,'partly_cloudy'),(2,0,'partly_cloudy_night'),
                             (3,1,'cloud'),(45,1,'fog'),(51,1,'drizzle'),(61,1,'rain'),(65,1,'heavy_rain'),
                             (66,1,'freezing_rain'),(71,1,'snow'),(75,1,'heavy_snow'),(95,1,'thunderstorm'),(99,1,'storm_hail')]:
            self.assertEqual(condition(dict(weather_code=code,is_day=day))[1],key)
        self.assertEqual(condition(dict(weather_code=61,is_day=1,rain=1,snowfall=1))[1],'sleet')
        self.assertEqual(condition(dict(weather_code=0,is_day=1,wind_speed_10m=60))[1],'wind')

    def test_misaligned_timelines_stale_wrong_city_and_corrupt_cache_are_rejected(self):
        now=time.time();raw=response(now);raw['hourly']['temperature_2m'].pop()
        with self.assertRaises(ValueError):fetch_forecast(CITY,now,Mock(return_value=raw))
        good=forecast(now)
        self.assertFalse(cache_valid(good,dict(CITY,city='Milano'),now))
        self.assertFalse(cache_valid(good,CITY,now+86401))
        for alter in (lambda d:d['hourly'][0].update(temperature_2m='bad'),
                      lambda d:d['current'].pop('time'),lambda d:d.update(timezone='x'*101),
                      lambda d:d['daily'][0].update(precipitation_probability_max=200)):
            data=copy.deepcopy(good);alter(data);self.assertFalse(cache_valid(data,CITY,now))


class ForecastUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)
        self.store.set_preference('updates_enabled',False);self.pet=Companion(self.store)
        self.pet.timer.stop();self.pet.reminder_timer.stop();self.pet.study_tools.timer.stop()
        self.pet.context.enabled={k:False for k in ('greeting','time','weather')}
    def tearDown(self):
        self.pet.close();self.pet.deleteLater();app.processEvents();self.store.close();self.tmp.cleanup()
    def page(self):
        self.pet.context.set_weather_location(CITY);self.store.set_preference('weather_forecast_cache',forecast())
        self.pet.open_panel(tab=7);app.processEvents();return self.pet.panel.weather_view

    def test_lazy_city_gate_cached_load_hour_selection_and_hidden_timer(self):
        self.pet.open_panel(tab=0);app.processEvents();panel=self.pet.panel
        self.assertIsNone(panel.weather_view);self.assertFalse(panel.nav[(7,None)].isVisible())
        self.assertIsNone(getattr(self.pet.context,'forecast',None))
        page=self.page();self.assertIsNotNone(page);self.assertIsNone(page.service.process)
        self.assertTrue(page.timer.isActive());self.assertEqual(len([b for b in page.days if b.isVisible()]),7)
        page.select_day(1);self.assertEqual(page.hours.topLevelItemCount(),24)
        page.hours.setCurrentItem(page.hours.topLevelItem(3));self.assertIn('03:00',page.when.text())
        self.assertLessEqual(len(page.art),3)
        panel.show_page(0);app.processEvents();self.assertFalse(page.timer.isActive())
        self.pet.context.set_weather_location(None);app.processEvents()
        self.assertFalse(panel.nav[(7,None)].isVisible());self.assertIsNone(page.service.data)

    def test_cache_persists_failures_keep_old_data_and_retry_is_bounded(self):
        page=self.page();service=page.service;cached=service.data
        failed=Mock();failed.location=CITY;failed.readAllStandardOutput.return_value=b'null';service.process=failed
        service.received(failed,0);self.assertIs(service.data,cached);self.assertTrue(service.failed)
        self.assertIn('Dati salvati',page.updated.text())
        with patch('yun_jin_forecast_service.QProcess') as process:service.request();process.assert_not_called()
        other=ForecastService(self.pet)
        try:self.assertEqual(other.data,cached)
        finally:other.shutdown();other.deleteLater()

    def test_old_worker_result_cannot_replace_a_new_city_and_shutdown_kills_worker(self):
        page=self.page();service=page.service;old=Mock();service.process=old
        self.pet.context.set_weather_location(dict(CITY,city='Milano',latitude=45.46,longitude=9.19))
        old.kill.assert_called_once();service.received(old,0);old.readAllStandardOutput.assert_not_called()
        self.assertIsNone(service.data)
        worker=Mock();service.process=worker;service.shutdown();worker.kill.assert_called_once()
        service.request();self.assertIsNone(service.process)

    def test_local_hours_follow_city_timezone_and_daylight_saving(self):
        page=self.page();page.zone=QTimeZone(b'Europe/Rome')
        # 25 Oct 2026, 00:30 and 01:30 UTC are both local 02:30, on opposite sides of DST.
        from datetime import datetime,timezone
        a=datetime(2026,10,25,0,30,tzinfo=timezone.utc).timestamp()
        self.assertEqual(page.local(a).toString('HH:mm'),'02:30')
        self.assertEqual(page.local(a+3600).toString('HH:mm'),'02:30')
        page.zone=QTimeZone(b'Asia/Kolkata')
        self.assertEqual(page.local(a).toString('HH:mm'),'06:00')

    def wait(self,predicate):
        end=time.monotonic()+5
        while not predicate() and time.monotonic()<end:
            loop=QEventLoop();QTimer.singleShot(10,loop.quit);loop.exec()
        self.assertTrue(predicate(),'Forecast worker timed out')

    def test_real_worker_protocol_and_missing_interpreter_fail_without_dialogs(self):
        page=self.page();service=page.service;root=Path(self.tmp.name)
        (root/'yun_jin_weather.py').write_text('import sys,json\njob=json.load(sys.stdin)\nprint('+repr(json.dumps(forecast()))+')\n',encoding='utf-8')
        with patch('yun_jin_forecast_service.BASE',root):
            service.request(True);self.assertIsNotNone(service.process)
            self.wait(lambda:service.process is None)
        self.assertFalse(service.failed);self.assertFalse(service.timeout.isActive())
        service.last_attempt=-1e10
        with patch.object(self.pet.study_tools,'worker_python',return_value=str(root/'missing-python')):
            service.request(True);self.wait(lambda:service.process is None)
        self.assertTrue(service.failed);self.assertIsNotNone(service.data)
        self.assertFalse(service.timeout.isActive())

    def test_immediate_start_failure_does_not_leave_a_late_timeout(self):
        class FailedProcess(QObject):
            ProcessError=QProcess.ProcessError
            started=pyqtSignal()
            finished=pyqtSignal(int,int)
            errorOccurred=pyqtSignal(object)
            def setProgram(self,value):pass
            def setArguments(self,value):pass
            def start(self):self.errorOccurred.emit(self.ProcessError.FailedToStart)
            def readAllStandardOutput(self):return b''
        page=self.page();service=page.service;cached=service.data
        with patch('yun_jin_forecast_service.QProcess',FailedProcess):service.request(True)
        self.assertIsNone(service.process);self.assertTrue(service.failed)
        self.assertIs(service.data,cached);self.assertFalse(service.timeout.isActive())
        self.assertGreater(service.retry_at,time.monotonic())
        # The same startup ordering also matters for city search and ambient weather.
        from yun_jin_weather_ui import CityDialog
        dialog=CityDialog(self.pet,self.pet.panel)
        try:
            dialog.query.setText('Reggio Calabria')
            with patch('yun_jin_weather_ui.QProcess',FailedProcess):dialog.start_search()
            self.assertIsNone(dialog.process);self.assertFalse(dialog.timeout.isActive())
            self.assertTrue(dialog.search.isEnabled())
        finally:dialog.reject();dialog.deleteLater()
        context=self.pet.context;context.enabled['weather']=True
        with patch('yun_jin_context.QProcess',FailedProcess):context.request_weather()
        self.assertIsNone(context.process);self.assertFalse(context.timeout.isActive())

    def test_small_window_fits_days_and_generated_art_cache_stays_bounded(self):
        page=self.page();self.pet.panel.resize(760,550)
        for _ in range(5):app.processEvents()
        for b in page.days:
            self.assertLessEqual(b.geometry().right(),page.day_box.width())
            self.assertGreaterEqual(b.height(),b.sizeHint().height())
        row=dict(page.service.data['current'])
        for code in (0,2,3,45,51,61,65,66,71,75,95,99):
            row.update(weather_code=code,is_day=1);page.show_conditions(row)
            self.assertFalse(page.picture.pixmap().isNull())
            self.assertLessEqual(len(page.art),3)
        self.assertLess(sum(p.width()*p.height()*4 for p in page.art.values()),2*1024*1024)


if __name__=='__main__':unittest.main(verbosity=2)
