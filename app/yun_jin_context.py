# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional ambient reactions; bounded state, slow clocks and no network on the GUI thread."""
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from PyQt6.QtCore import QObject, QProcess, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication
from yun_jin_core import BASE, ANIMATIONS
from yun_jin_weather import fresh, location_valid, selected_location, WEATHER_TTL

GREETINGS = {
    'it': {
        'morning': 'Buongiorno! Ti auguro una bella giornata.',
        'afternoon': 'Buon pomeriggio! Sono felice di rivederti.',
        'evening': 'Buonasera! Com’è andata la giornata?',
        'night': 'È tardi. Ricordati di riposare un po’.',
    },
    'en': {
        'morning': 'Good morning! I hope you have a lovely day.',
        'afternoon': 'Good afternoon! It’s lovely to see you again.',
        'evening': 'Good evening! How was your day?',
        'night': 'It’s getting late. Remember to get some rest.',
    },
    'zh-CN': {
        'morning': '早上好！愿你今天心情愉快。',
        'afternoon': '下午好！很高兴又见到你。',
        'evening': '晚上好！今天过得怎么样？',
        'night': '夜深了，别忘了早点休息。',
    },
}
TIME_ANIMATIONS = {'morning': ('morning16', 'wave'), 'afternoon': ('afternoon16', 'wave'),
                   'evening': ('evening16', 'review'), 'night': ('yawn16', 'wait')}
WEATHER_REACTIONS = {
    'sun': ('sun16', 'wave'), 'clear_night': ('review', 'review'),
    'cloud': ('cloud16', 'review'), 'fog': ('wait', 'wait'),
    'rain': ('rain16', 'wait'), 'snow': ('snow16', 'wave'), 'storm': ('rain16', 'review'),
}
WEATHER_LINES = {
    'it': {
        'sun': 'Che bel sole! Spero che illumini anche la tua giornata.',
        'clear_night': 'Il cielo è sereno. Che bella notte tranquilla.',
        'cloud': 'Oggi è nuvoloso. Possiamo prendercela con calma.',
        'fog': 'Fuori c’è nebbia. Fai attenzione se esci.',
        'rain': 'Piove. Se esci, ricordati l’ombrello.',
        'snow': 'Nevica! Copriti bene se esci.',
        'storm': 'C’è un temporale. Qui al riparo si sta meglio.',
    },
    'en': {
        'sun': 'Such lovely sunshine! I hope it brightens your day too.',
        'clear_night': 'The sky is clear. What a peaceful night.',
        'cloud': 'It’s cloudy today. We can take things slowly.',
        'fog': 'It’s foggy outside. Take care if you go out.',
        'rain': 'It’s raining. Remember your umbrella if you go out.',
        'snow': 'It’s snowing! Wrap up warmly if you go out.',
        'storm': 'There’s a thunderstorm outside. It’s cosy in here.',
    },
    'zh-CN': {
        'sun': '阳光真好，愿你今天心情愉快。',
        'clear_night': '今晚天色晴朗，真是个宁静的夜晚。',
        'cloud': '今天多云，慢慢来，也很好。',
        'fog': '外面有雾，出门记得小心。',
        'rain': '外面下雨了，出门记得带伞。',
        'snow': '下雪了！出门记得保暖。',
        'storm': '外面有雷雨，待在室内要安心些。',
    },
}


def contextual_line(table, key, language):
    return table.get(language, table['it'])[key]


def time_period(now):
    """Night spans midnight. A high-water key prevents replay after clock rollback."""
    hour = now.hour
    day = now.date().toordinal()
    if 5 <= hour < 12: return day*4, 'morning'
    if 12 <= hour < 18: return day*4+1, 'afternoon'
    if 18 <= hour < 22: return day*4+2, 'evening'
    return (day if hour >= 22 else day-1)*4+3, 'night'


class Context(QObject):
    location_changed=pyqtSignal()
    def __init__(self, pet, clock=datetime.now, monotonic=time.monotonic, wall=time.time):
        super().__init__(pet)
        self.pet = pet
        self.clock, self.monotonic, self.wall = clock, monotonic, wall
        self.enabled = {key: bool(pet.store.preference('context_'+key, True))
                        for key in ('greeting', 'time', 'weather')}
        self.started = False; self.closed = False; self.period = None
        self.pending = {}; self.process = None; self.generation = 0
        self.next_weather = 0.; self.weather_result = None; self.last_weather_kind = None
        self.weather_location=selected_location(pet.store.preference('context_weather_location',None))
        # Discard the old IP estimate; never promote it to a chosen city.
        if pet.store.preference('context_location_cache',None) is not None:
            pet.store.set_preference('context_location_cache',None)
        cache=pet.store.preference('context_weather_cache',None)
        if cache is not None and (not isinstance(cache,dict)
                or not isinstance(cache.get('location'),dict)
                or cache['location'].get('source')!='manual'):
            pet.store.set_preference('context_weather_cache',None)
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
        if self.enabled['weather'] and self.weather_location is not None:
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

    def can_react(self, ignore_speech=False, serial=None, ignore_character=False):
        p = self.pet
        allowed_state = p.state == 'idle' or (serial is not None and p.state == 'action' and serial == p.action_serial)
        character_ready=(allowed_state and not p.paused and not p.locked and p.drag_anchor is None
                         and not p.following and p.mode!='asleep' and not p.is_sleeping() and not p.pending_feedback
                         and not getattr(p,'character_hidden',False) and not getattr(p,'fullscreen_hidden',False))
        return bool(not self.closed and not p.closing and (ignore_character or character_ready)
                    and (serial is None or serial == p.action_serial) and not p.menu_open
                    and not p.metronome.running and not p.focus_active()
                    and not p.due_count and not p.reminder_dialog
                    and not (getattr(p,'study_tools',None) and p.study_tools.active_dialog and p.study_tools.active_dialog.isVisible())
                    and not (getattr(p,'study_tools',None) and p.study_tools.prompt and p.study_tools.prompt.isVisible())
                    and not (p.panel and p.panel.isVisible() and not p.panel.isMinimized()) and QApplication.activeModalWidget() is None and QApplication.activePopupWidget() is None
                    and (ignore_speech or not p.speech.busy))

    def dispatch(self):
        if not self.started or self.closed: return
        now = self.monotonic()
        self.pending = {k:v for k,v in self.pending.items() if self.enabled[k] and now <= v[0]}
        if not self.pending or not self.can_react() or now-self.last_reaction < 60: return
        kind = next(k for k in ('greeting', 'time', 'weather') if k in self.pending)
        _, value = self.pending.pop(kind)
        self.last_reaction = now
        language = self.pet.speech.pref('language', 'it')
        text = None
        if kind in ('greeting', 'time'):
            animation, fallback = TIME_ANIMATIONS[value]
            if kind == 'greeting':
                text = contextual_line(GREETINGS, value, language)
        else:
            animation, fallback = WEATHER_REACTIONS[value]
            text = contextual_line(WEATHER_LINES, value, language)
            self.pet.store.set_preference('context_weather_reaction', {'kind': value, 'at': self.wall()})
        tag = {'kind': kind, 'serial': self.pet.action_serial,
               'animation': (animation, fallback)}
        # Prepare the voice first: a short gesture can finish before TTS is ready.
        if text and self.pet.speech.speak(text, category='ambient', tag=tag):
            return
        self.play_speech_animation(tag)

    def play_speech_animation(self, tag):
        """One gesture at playback start, or silently if speech is unavailable."""
        animation = tag.pop('animation', None)
        kind = tag.get('kind')
        if (not animation or not self.enabled.get(kind, False)
                or (kind == 'greeting' and not self.enabled['time'])
                or not self.can_react(ignore_speech=True, serial=tag.get('serial'))):
            return
        name, fallback = animation
        if not self.pet.use_extra_animations or name not in ANIMATIONS: name = fallback
        self.pet.sequence([(name, 1)])
        tag['serial'] = self.pet.action_serial

    def valid_weather(self, result):
        valid=(isinstance(result, dict) and isinstance(result.get('kind'), str) and result['kind'] in WEATHER_REACTIONS
                and fresh(result.get('checked'), self.wall(), WEATHER_TTL)
                and fresh(result.get('observed'), self.wall(), 7200)
                and location_valid(result.get('location')))
        if not valid or self.weather_location is None:return False
        location=result['location']
        return (location.get('source')=='manual' and all(location[key]==self.weather_location[key]
                for key in ('latitude','longitude')))

    def set_weather_location(self, location):
        choice=selected_location(location)
        if location is not None and choice is None:raise ValueError('Città non valida.')
        if choice==self.weather_location:return
        self.cancel_request()
        self.weather_location=choice
        self.pet.store.set_preference('context_weather_location',choice)
        self.pet.store.set_preference('context_weather_cache',None)
        self.pet.store.set_preference('context_weather_reaction',None)
        self.weather_result=None;self.last_weather_kind=None;self.pending.pop('weather',None)
        speech=self.pet.speech
        if speech.category=='ambient' and speech.current_tag and speech.current_tag.get('kind')=='weather':
            speech.stop(announce=False)
        self.next_weather=self.monotonic()
        self.location_changed.emit()
        if choice is not None and self.started and self.enabled['weather'] and not self.closed:self.request_weather()

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
        if self.closed or self.process is not None or not self.enabled['weather'] or self.weather_location is None: return
        forecast=getattr(self,'forecast',None)
        if forecast is not None and forecast.process is not None:
            self.next_weather=self.monotonic()+60;return
        self.next_weather = self.monotonic()+WEATHER_TTL  # One attempt/hour, including failures.
        self.generation += 1; generation = self.generation
        process = QProcess(self); self.process = process
        executable = Path(sys.executable)
        if sys.platform == 'win32' and executable.name.lower() == 'pythonw.exe':
            candidate = executable.with_name('python.exe')
            if candidate.is_file(): executable = candidate
        process.setProgram(str(executable)); process.setArguments([str(BASE/'yun_jin_weather.py')])
        payload = json.dumps({'location':self.weather_location}).encode('utf-8')
        def send():
            if process is self.process:
                process.write(payload); process.closeWriteChannel()
        process.started.connect(send)
        process.finished.connect(lambda code, status: self.received(process, generation, code))
        process.errorOccurred.connect(lambda error: self.failed(process) if error == QProcess.ProcessError.FailedToStart else None)
        # start() can emit FailedToStart before returning on Windows.
        self.timeout.start(12000); process.start()

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
        if getattr(self,'forecast',None) is not None:self.forecast.shutdown()
        self.cancel_request()
        # Include a request just cancelled by a checkbox/timeout whose finished
        # signal has not yet been delivered. No child process survives closing.
        for process in self.findChildren(QProcess):
            if process.state() != QProcess.ProcessState.NotRunning:
                process.kill(); process.waitForFinished(250)
