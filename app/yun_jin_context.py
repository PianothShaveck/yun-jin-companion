# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional ambient reactions; bounded state, slow clocks and no network on the GUI thread."""
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from PyQt6.QtCore import QObject, QProcess, QTimer, Qt
from PyQt6.QtWidgets import QApplication
from yun_jin_core import BASE, ANIMATIONS
from yun_jin_weather import fresh, location_valid, WEATHER_TTL

GREETINGS = {
    'morning': '早上好！愿你今天心情愉快。',
    'afternoon': '下午好！很高兴又见到你。',
    'evening': '晚上好！今天辛苦了。',
    'night': '夜深了，别忘了早点休息。',
}
TIME_ANIMATIONS = {'morning': ('stretch16', 'wave'), 'afternoon': ('work', 'work'),
                   'evening': ('pirouette16', 'review'), 'night': ('stretch16', 'wait')}
WEATHER_REACTIONS = {
    'sun': ('celebrate16', 'wave', '阳光真好，愿你今天心情愉快。'),
    'clear_night': ('review', 'review', '今晚天色晴朗，真是个宁静的夜晚。'),
    'cloud': ('review', 'review', '今天多云，慢慢来，也很好。'),
    'fog': ('wait', 'wait', '外面有雾，出门记得小心。'),
    'rain': ('wait', 'wait', '外面下雨了，出门记得带伞。'),
    'snow': ('celebrate16', 'wave', '下雪了！出门记得保暖。'),
    'storm': ('review', 'review', '外面有雷雨，待在室内要安心些。'),
}


def time_period(now):
    """Night spans midnight. A high-water key prevents replay after clock rollback."""
    hour = now.hour
    day = now.date().toordinal()
    if 5 <= hour < 12: return day*4, 'morning'
    if 12 <= hour < 18: return day*4+1, 'afternoon'
    if 18 <= hour < 22: return day*4+2, 'evening'
    return (day if hour >= 22 else day-1)*4+3, 'night'


class Context(QObject):
    def __init__(self, pet, clock=datetime.now, monotonic=time.monotonic, wall=time.time):
        super().__init__(pet)
        self.pet = pet
        self.clock, self.monotonic, self.wall = clock, monotonic, wall
        self.enabled = {key: bool(pet.store.preference('context_'+key, True))
                        for key in ('greeting', 'time', 'weather')}
        self.started = False; self.closed = False; self.period = None
        self.pending = {}; self.process = None; self.generation = 0
        self.next_weather = 0.; self.weather_result = None; self.last_weather_kind = None
        self.last_reaction = -1e10
        self.timer = QTimer(self); self.timer.setInterval(60000)
        self.timer.setTimerType(Qt.TimerType.VeryCoarseTimer); self.timer.timeout.connect(self.poll)
        self.timeout = QTimer(self); self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self.cancel_request)

    def start(self):
        if self.started or self.closed: return
        self.started = True
        self.poll(initial=True)
        self.timer.start()

    def set_enabled(self, key, value):
        if key not in self.enabled: return
        self.enabled[key] = bool(value)
        self.pet.store.set_preference('context_'+key, bool(value))
        if not value:
            self.pending.pop(key, None)
            if key == 'weather': self.cancel_request()
            speech = self.pet.speech
            if speech.category == 'ambient' and speech.current_tag and speech.current_tag.get('kind') == key:
                speech.stop(announce=False)
        elif key == 'weather':
            # No immediate network call or repeated reaction on checkbox toggles.
            self.next_weather = min(self.next_weather, self.monotonic()+60)

    def poll(self, initial=False):
        if self.closed: return
        now = self.monotonic()
        try:
            key, period = time_period(self.clock())
            if self.period is None:
                self.period = key
                if initial and self.enabled['greeting']:
                    self.pending['greeting'] = (now+45, period)
            elif key > self.period:
                self.period = key
                self.pending.pop('greeting', None)
                if self.enabled['time']:
                    self.pending['time'] = (now+300, period)
        except Exception:
            pass
        if self.enabled['weather']:
            if initial:
                self.next_weather = now+60  # Never compete with app startup / its greeting.
                cache = self.pet.store.preference('context_weather_cache', None)
                if self.valid_weather(cache): self.weather_result = cache
            elif now >= self.next_weather and self.process is None:
                if self.valid_weather(self.weather_result):
                    self.queue_weather(self.weather_result)
                    self.next_weather = now+60
                else:
                    self.request_weather()
        self.dispatch()

    def can_react(self, ignore_speech=False, serial=None):
        p = self.pet
        allowed_state = p.state == 'idle' or (serial is not None and p.state == 'action' and serial == p.action_serial)
        return bool(not self.closed and not p.closing and allowed_state and not p.paused and not p.locked
                    and not p.menu_open and p.drag_anchor is None and not p.following and p.mode != 'asleep'
                    and not p.is_sleeping() and not p.metronome.running and not p.focus_active()
                    and not p.due_count and not p.pending_feedback and not p.reminder_dialog
                    and not (p.panel and p.panel.isVisible()) and QApplication.activeModalWidget() is None and QApplication.activePopupWidget() is None
                    and (ignore_speech or not p.speech.busy))

    def dispatch(self):
        if not self.started or self.closed: return
        now = self.monotonic()
        self.pending = {k:v for k,v in self.pending.items() if self.enabled[k] and now <= v[0]}
        if not self.pending or not self.can_react() or now-self.last_reaction < 60: return
        kind = next(k for k in ('greeting', 'time', 'weather') if k in self.pending)
        _, value = self.pending.pop(kind)
        self.last_reaction = now
        if kind == 'greeting':
            self.pet.speech.speak(GREETINGS[value], category='ambient', language='zh-CN', tag={'kind': kind})
            return
        if kind == 'time':
            animation, fallback = TIME_ANIMATIONS[value]; text = None
        else:
            animation, fallback, text = WEATHER_REACTIONS[value]
            self.pet.store.set_preference('context_weather_reaction', {'kind': value, 'at': self.wall()})
        if not self.pet.use_extra_animations or animation not in ANIMATIONS: animation = fallback
        self.pet.sequence([(animation, 1)])
        if text:
            self.pet.speech.speak(text, category='ambient', language='zh-CN',
                                  tag={'kind': kind, 'serial': self.pet.action_serial})

    def valid_weather(self, result):
        return (isinstance(result, dict) and isinstance(result.get('kind'), str) and result['kind'] in WEATHER_REACTIONS
                and fresh(result.get('checked'), self.wall(), WEATHER_TTL)
                and fresh(result.get('observed'), self.wall(), 7200)
                and location_valid(result.get('location')))

    def queue_weather(self, result):
        if self.last_weather_kind == result['kind']: return
        self.pending.pop('weather', None)
        previous = self.pet.store.preference('context_weather_reaction', {})
        if not isinstance(previous, dict): previous = {}
        if previous.get('kind') == result['kind']:
            self.last_weather_kind = result['kind']
            return
        if fresh(previous.get('at'), self.wall(), 7200): return
        self.last_weather_kind = result['kind']
        self.pending['weather'] = (self.monotonic()+300, result['kind'])

    def request_weather(self):
        if self.closed or self.process is not None or not self.enabled['weather']: return
        self.next_weather = self.monotonic()+WEATHER_TTL  # One attempt/hour, including failures.
        self.generation += 1; generation = self.generation
        process = QProcess(self); self.process = process
        executable = Path(sys.executable)
        if sys.platform == 'win32' and executable.name.lower() == 'pythonw.exe':
            candidate = executable.with_name('python.exe')
            if candidate.is_file(): executable = candidate
        process.setProgram(str(executable)); process.setArguments([str(BASE/'yun_jin_weather.py')])
        location = self.pet.store.preference('context_location_cache', None)
        payload = json.dumps({'location': location}).encode('utf-8')
        def send():
            if process is self.process:
                process.write(payload); process.closeWriteChannel()
        process.started.connect(send)
        process.finished.connect(lambda code, status: self.received(process, generation, code))
        process.errorOccurred.connect(lambda error: self.failed(process) if error == QProcess.ProcessError.FailedToStart else None)
        process.start(); self.timeout.start(12000)

    def failed(self, process):
        if process is self.process:
            self.process = None; self.timeout.stop()
        process.deleteLater()

    def received(self, process, generation, code):
        if process is not self.process:
            process.deleteLater(); return
        self.process = None; self.timeout.stop()
        raw = bytes(process.readAllStandardOutput()); process.deleteLater()
        if self.closed or not self.enabled['weather'] or generation != self.generation or code != 0 or len(raw) > 32768: return
        try:
            result = json.loads(raw)
            if not self.valid_weather(result): return
            self.weather_result = result
            self.pet.store.set_preference('context_weather_cache', result)
            self.pet.store.set_preference('context_location_cache', result['location'])
            self.queue_weather(result)
            self.dispatch()
        except Exception:
            pass

    def cancel_request(self):
        self.generation += 1; self.timeout.stop()
        process, self.process = self.process, None
        if process is not None: process.kill()
        return process

    def shutdown(self):
        self.closed = True; self.pending.clear(); self.timer.stop()
        self.cancel_request()
        # Include a request just cancelled by a checkbox/timeout whose finished
        # signal has not yet been delivered. No child process survives closing.
        for process in self.findChildren(QProcess):
            if process.state() != QProcess.ProcessState.NotRunning:
                process.kill(); process.waitForFinished(250)
