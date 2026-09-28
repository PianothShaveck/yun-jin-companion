# SPDX-License-Identifier: GPL-3.0-or-later
"""Sample-clock metronome and persistent stopwatch. No external audio package."""
from array import array
from collections import deque
from dataclasses import dataclass, asdict
from fractions import Fraction
import math
import sys
import time
from PyQt6.QtCore import QObject, QIODevice, QTimer, pyqtSignal

@dataclass(frozen=True)
class MetroConfig:
    bpm: int = 80
    accent: int = 4                 # 0 = every click has the same sound
    ramp: bool = False
    target: int = 120
    step: int = 4
    every: int = 16
    unit: str = 'beats'             # beats or seconds
    finish: str = 'hold'            # hold or stop after the final interval

    def validate(self):
        if not 20 <= self.bpm <= 400 or not 20 <= self.target <= 400:
            raise ValueError('I BPM devono essere tra 20 e 400.')
        if not 0 <= self.accent <= 32 or not 1 <= self.step <= 100 or not 1 <= self.every <= 3600:
            raise ValueError('Accento, incremento o intervallo non valido.')
        if self.unit not in ('beats','seconds') or self.finish not in ('hold','stop'):
            raise ValueError('Modalità di scalata non valida.')
        return self

class BeatPlan:
    """Rational beat onsets: rounding only happens at the audio sample boundary."""
    def __init__(self, config, sample_rate):
        self.config=config.validate();self.rate=sample_rate
        self.index=0;self.onset=Fraction(0)
        self.stage=0;self.stage_start=Fraction(0)

    def next(self):
        c=self.config
        if c.ramp and c.unit=='seconds' and self.onset-self.stage_start>=c.every:
            self.stage+=1;self.stage_start=self.onset
        stage=(self.index//c.every if c.unit=='beats' else self.stage) if c.ramp else 0
        last_stage=math.ceil(abs(c.target-c.bpm)/c.step)
        if c.ramp and c.finish=='stop' and stage>last_stage:
            return None
        direction=1 if c.target>=c.bpm else -1
        bpm=c.bpm+direction*min(abs(c.target-c.bpm),stage*c.step) if c.ramp else c.bpm
        event=(round(self.onset*self.rate), self.index, bpm, bool(c.accent and self.index%c.accent==0))
        self.index+=1;self.onset+=Fraction(60,bpm)
        return event

class ClickStream:
    """Continuous PCM, invariant to chunk size; no timer-triggered sound files."""
    def __init__(self,config,rate=48000,channels=2):
        self.plan=BeatPlan(config,rate);self.rate=rate;self.channels=channels
        self.frame=0;self.events=deque();self.next_event=self.plan.next()
        self.stop_at=None;self.active=[]
        self.clicks={False:self.make_click(1200),True:self.make_click(2000)}

    def make_click(self,frequency):
        frames=round(self.rate*.022);samples=array('h')
        for i in range(frames):
            t=i/self.rate
            envelope=min(1,i/max(1,self.rate*.0007))*math.exp(-t*230)
            value=int(15000*envelope*(.78*math.sin(2*math.pi*frequency*t)+.22*math.sin(2*math.pi*frequency*2.7*t)))
            samples.extend([value]*self.channels)
        if sys.byteorder!='little':samples.byteswap()
        return samples.tobytes()

    def render(self,nframes):
        if nframes<0:raise ValueError('negative frame count')
        end=self.frame+nframes;bpf=2*self.channels;output=bytearray(nframes*bpf)
        while self.next_event is not None and self.next_event[0]<end:
            event=self.next_event;self.events.append(event)
            self.active.append((event[0],self.clicks[event[3]]))
            self.next_event=self.plan.next()
            if self.next_event is None:
                self.stop_at=round(self.plan.onset*self.rate)
        keep=[]
        for onset,pcm in self.active:
            click_end=onset+len(pcm)//bpf
            left=max(self.frame,onset);right=min(end,click_end)
            if right>left:
                output[(left-self.frame)*bpf:(right-self.frame)*bpf]=pcm[(left-onset)*bpf:(right-onset)*bpf]
            if click_end>end:keep.append((onset,pcm))
        self.active=keep;self.frame=end
        return bytes(output)

class AudioFeed(QIODevice):
    def __init__(self,stream,parent=None):
        super().__init__(parent);self.stream=stream;self.tail=b''
        self.open(QIODevice.OpenModeFlag.ReadOnly)
    def isSequential(self):return True
    def bytesAvailable(self):return 65536+super().bytesAvailable()
    def readData(self,size):
        bpf=self.stream.channels*2
        count=max(0,math.ceil((size-len(self.tail))/bpf))
        data=self.tail+self.stream.render(count)
        self.tail=data[size:]
        return data[:size]
    def writeData(self,data):return -1

class Metronome(QObject):
    changed=pyqtSignal()
    beat=pyqtSignal(int,int,bool)
    active_changed=pyqtSignal(bool)
    def __init__(self,pet):
        super().__init__(pet);self.pet=pet;self.running=False
        self.sink=None;self.feed=None;self.stream=None
        self.status='Pronto.';self.index=0;self.bpm=80;self.accented=False
        self.last_onset=0;self.position=0
        self.volume=int(pet.store.preference('metro_volume',55))
        self.timer=QTimer(self);self.timer.setInterval(16);self.timer.timeout.connect(self.poll)
        self.wall_poll=0.;self.idle_since=None
    def settings(self):
        raw=self.pet.store.preference('metronome',{})
        try:return MetroConfig(**raw).validate()
        except (TypeError,ValueError):return MetroConfig()
    def start(self,config):
        from PyQt6.QtMultimedia import QAudioSink,QAudioFormat,QMediaDevices
        self.stop(announce=False)
        config.validate();device=QMediaDevices.defaultAudioOutput()
        if device.isNull():
            self.status='Nessuna uscita audio disponibile. Collega cuffie o altoparlanti.';self.changed.emit();return False
        fmt=None
        for rate in dict.fromkeys([device.preferredFormat().sampleRate(),48000,44100]):
            if rate<=0:continue
            for channels in [2,1]:
                candidate=QAudioFormat();candidate.setSampleRate(rate);candidate.setChannelCount(channels)
                candidate.setSampleFormat(QAudioFormat.SampleFormat.Int16)
                if device.isFormatSupported(candidate):fmt=candidate;break
            if fmt is not None:break
        if fmt is None:
            self.status='L’uscita selezionata non supporta il formato PCM del metronomo.';self.changed.emit();return False
        self.pet.store.set_preference('metronome',asdict(config))
        self.stream=ClickStream(config,fmt.sampleRate(),fmt.channelCount())
        self.feed=AudioFeed(self.stream,self)
        self.sink=QAudioSink(device,fmt,self)
        self.sink.setBufferSize(round(fmt.sampleRate()*.08)*fmt.bytesPerFrame())
        self.sink.setVolume(self.volume/100)
        self.sink.stateChanged.connect(self.audio_state)
        self.index=0;self.bpm=config.bpm;self.last_onset=0;self.position=0
        self.running=True;self.wall_poll=time.time();self.idle_since=None
        self.sink.start(self.feed)
        if not self.running:return False
        self.status='In esecuzione';self.timer.start();self.active_changed.emit(True);self.changed.emit()
        return True
    def audio_state(self,state):
        from PyQt6.QtMultimedia import QAudio
        if not self.running or self.sink is None:return
        if self.sink.error()!=QAudio.Error.NoError:
            self.stop(announce=False);self.status='Audio interrotto: controlla l’uscita e premi Avvia.';self.changed.emit()
    def poll(self):
        if not self.running or self.sink is None:return
        now=time.time()
        if now-self.wall_poll>3:
            self.stop(announce=False);self.status='Metronomo fermato dopo una sospensione: premi Avvia.';self.changed.emit();return
        self.wall_poll=now
        self.position=round(self.sink.processedUSecs()*self.stream.rate/1_000_000)
        latest=None
        while self.stream.events and self.stream.events[0][0]<=self.position:
            latest=self.stream.events.popleft()
        if latest:
            self.last_onset,self.index,self.bpm,self.accented=latest
            self.beat.emit(self.index,self.bpm,self.accented)
        if self.stream.stop_at is not None and self.position>=self.stream.stop_at:
            self.stop(announce=False);self.status='Scalata completata.';self.changed.emit()
    def phase(self):
        if not self.running or not self.stream:return 0.
        return max(0.,min(.999,(self.position-self.last_onset)/self.stream.rate/(60/self.bpm)))
    def set_volume(self,value):
        self.volume=max(0,min(100,int(value)));self.pet.store.set_preference('metro_volume',self.volume)
        if self.sink:self.sink.setVolume(self.volume/100)
    def stop(self,announce=True):
        was=self.running;self.running=False;self.timer.stop()
        sink,self.sink=self.sink,None
        if sink:sink.reset();sink.deleteLater()
        if self.feed:self.feed.close();self.feed.deleteLater();self.feed=None
        if was:self.active_changed.emit(False)
        if announce:self.status='Fermo.';self.changed.emit()

class Stopwatch(QObject):
    changed=pyqtSignal()
    def __init__(self,store,parent=None):
        super().__init__(parent);self.store=store;self.started=None
        saved=store.preference('stopwatch',{})
        self.accumulated=max(0.,float(saved.get('elapsed',0)))
        self.laps=list(saved.get('laps',[]))
    @property
    def running(self):return self.started is not None
    def elapsed(self):
        return self.accumulated+(time.monotonic()-self.started if self.running else 0.)
    def start(self):
        if not self.running:self.started=time.monotonic();self.changed.emit()
    def pause(self):
        if self.running:self.accumulated=self.elapsed();self.started=None
        self.save();self.changed.emit()
    def reset(self):
        self.started=None;self.accumulated=0.;self.laps=[];self.save();self.changed.emit()
    def lap(self):
        if not self.running:return None
        total=self.elapsed();previous=self.laps[-1]['total'] if self.laps else 0.
        lap={'total':total,'split':total-previous};self.laps.append(lap);self.save();self.changed.emit();return lap
    def save(self):
        self.store.set_preference('stopwatch',{'elapsed':self.elapsed(),'laps':self.laps})

def format_elapsed(seconds):
    tenths=max(0,int(seconds*10));h,rest=divmod(tenths,36000);m,rest=divmod(rest,600);s,t=divmod(rest,10)
    return f'{h:02d}:{m:02d}:{s:02d}.{t}'
