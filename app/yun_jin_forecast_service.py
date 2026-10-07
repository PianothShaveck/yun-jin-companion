# SPDX-License-Identifier: GPL-3.0-or-later
"""On-demand forecast cache; no permanent worker or idle polling timer."""
import json
import time
from PyQt6.QtCore import QObject,QProcess,QTimer,pyqtSignal
from yun_jin_core import BASE
from yun_jin_forecast import cache_valid,FORECAST_LIMIT,FORECAST_TTL
from yun_jin_weather import weather_kind


class ForecastService(QObject):
    changed=pyqtSignal()
    def __init__(self,pet):
        super().__init__(pet.context);self.pet=pet;self.process=None;self.closed=False
        self.failed=False;self.retry_at=0.;self.last_attempt=-1e10
        cached=pet.store.preference('weather_forecast_cache',None)
        self.data=cached if cache_valid(cached,self.location) else None
        self.timeout=QTimer(self);self.timeout.setSingleShot(True);self.timeout.timeout.connect(self.expired)
        pet.context.location_changed.connect(self.location_changed)

    @property
    def location(self):return self.pet.context.weather_location

    def request(self,force=False):
        now=time.monotonic()
        if self.closed or self.process is not None or not self.location:return
        if force:
            if now-self.last_attempt<30:return
        elif now<self.retry_at or cache_valid(self.data,self.location,ttl=FORECAST_TTL):return
        self.last_attempt=now;self.failed=False
        process=QProcess(self);self.process=process;process.location=dict(self.location)
        process.setProgram(self.pet.study_tools.worker_python())
        process.setArguments([str(BASE/'yun_jin_weather.py')])
        payload=json.dumps({'operation':'forecast','location':self.location}).encode()
        def send():
            if process is self.process:process.write(payload);process.closeWriteChannel()
        process.started.connect(send)
        process.finished.connect(lambda code,_:self.received(process,code))
        process.errorOccurred.connect(lambda error:self.received(process,-1)
                                      if error==QProcess.ProcessError.FailedToStart else None)
        process.start();self.timeout.start(8000);self.changed.emit()

    def received(self,process,code):
        if self.closed or process is not self.process:process.deleteLater();return
        self.process=None;self.timeout.stop()
        raw=bytes(process.readAllStandardOutput());process.deleteLater()
        try:
            if code or len(raw)>FORECAST_LIMIT or process.location!=self.location:raise ValueError()
            result=json.loads(raw)
            if not cache_valid(result,self.location,ttl=FORECAST_TTL):raise ValueError()
            self.data=result;self.retry_at=0.;self.failed=False
            self.pet.store.set_preference('weather_forecast_cache',result)
            # Reuse the same observation for the pet's ambient weather reaction.
            current=result['current'];kind=weather_kind(current.get('weather_code'),current.get('is_day'))
            ambient=dict(kind=kind,checked=result['checked'],observed=current['time'],
                         location=dict(self.location,source='manual'))
            context=self.pet.context
            if context.valid_weather(ambient):
                context.weather_result=ambient
                self.pet.store.set_preference('context_weather_cache',ambient)
        except (ValueError,TypeError,KeyError):self.failed=True;self.retry_at=time.monotonic()+900
        self.changed.emit()

    def expired(self):
        self.cancel();self.failed=True;self.retry_at=time.monotonic()+900;self.changed.emit()

    def cancel(self):
        self.timeout.stop();process,self.process=self.process,None
        if process is not None:process.kill()

    def location_changed(self):
        self.cancel();self.data=None;self.failed=False;self.retry_at=0.;self.last_attempt=-1e10
        self.pet.store.set_preference('weather_forecast_cache',None);self.changed.emit()

    def shutdown(self):
        self.closed=True;self.cancel()
