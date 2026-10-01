#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Yun Jin desktop pet — Python 3.11+ / PyQt6.

Place next to spritesheet-yun-jin-v2.png. Animation rows and gaze directions
come from that sheet, not from the annotated contact sheets or GIF previews.
"""
import ctypes
import hashlib
import json
import logging
import math
import random
import sys
import time
from collections import deque, OrderedDict
from collections.abc import Mapping
from pathlib import Path

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, QSettings, QLockFile, QStandardPaths
from PyQt6.QtGui import QActionGroup, QCursor, QIcon, QPainter, QPixmap, QRegion, QImageReader
from PyQt6.QtWidgets import QApplication, QWidget, QMenu, QMessageBox

BASE = Path(__file__).resolve().parent
# row, frame count, individual frame durations (seconds)
ANIMATIONS = {
    'idle': (0, 6, [0.48, 0.12, 0.46, 0.48, 0.12, 0.46]),
    'right': (1, 8, [0.085] * 8),
    'left': (2, 8, [0.085] * 8),
    'wave': (3, 4, [0.28, 0.40, 0.26, 0.34]),
    'jump': (4, 5, [0.17, 0.15, 0.23, 0.15, 0.22]),
    'failed': (5, 8, [0.28, 0.30, 0.30, 0.65, 0.45, 0.42, 0.32, 0.36]),
    'wait': (6, 6, [0.38] * 6),
    'work': (7, 6, [0.45, 0.50, 0.58, 0.50, 0.48, 0.62]),
    'review': (8, 6, [0.40, 0.48, 0.45, 0.52, 0.44, 0.48]),
}
BUILTIN_ANIMATIONS = frozenset(ANIMATIONS)
SLEEP_ANIMATIONS = ('sleep_in', 'sleep_loop', 'sleep_out')
CONTEXT_ANIMATIONS = frozenset(('morning16', 'afternoon16', 'evening16', 'yawn16', 'sun16', 'rain16', 'snow16', 'cloud16'))
LABELS = {
    'idle': 'Riposo', 'wave': 'Saluto', 'jump': 'Salto',
    'failed': 'Capitombolo', 'wait': 'In attesa',
    'work': 'Lavoro', 'review': 'Osserva',
    'left': 'Corsa a sinistra', 'right': 'Corsa a destra',
}


ANIMATION_GROUPS = (
    ('Gesti', ('wave', 'talking16', 'reminder16', 'celebrate16', 'applause16', 'greeting16')),
    ('Movimento', ('left', 'right', 'jump', 'failed', 'dance16', 'pirouette16', 'stretch16')),
    ('Attività', ('work', 'writing16', 'conduct16', 'stopwatch16')),
    ('Riposo', ('idle', 'wait', 'review', 'waiting16')),
    ('Orario', ('morning16', 'afternoon16', 'evening16', 'yawn16')),
    ('Meteo', ('sun16', 'cloud16', 'rain16', 'snow16')),
)


def gaze_index(dx, dy):
    """0 = up, 4 = right, 8 = down, 12 = left; clockwise."""
    return int((math.degrees(math.atan2(dx, -dy)) % 360 + 11.25) // 22.5) % 16


def clamp_to_screen(point, rect, width, height):
    # QRect origins can be negative on secondary monitors.
    return QPointF(max(rect.left(), min(point.x(), rect.right() + 1 - width)),
                   max(rect.top(), min(point.y(), rect.bottom() + 1 - height)))


def mac_all_spaces(widget):
    """Best effort native Spaces support; ordinary Qt always-on-top is the fallback.
    Only public Objective-C NSView/NSWindow methods; no Accessibility permission.
    Must run on the GUI thread after the native window exists.
    """
    if sys.platform != 'darwin':
        return
    try:
        objc = ctypes.CDLL('/usr/lib/libobjc.A.dylib')
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ctypes.c_void_p
        addr = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value
        def send(obj, name, result, argtypes=(), args=()):
            fn = ctypes.CFUNCTYPE(result, ctypes.c_void_p, ctypes.c_void_p, *argtypes)(addr)
            return fn(obj, objc.sel_registerName(name), *args)
        view = int(widget.winId())
        window = send(view, b'window', ctypes.c_void_p)
        if window:
            behavior = send(window, b'collectionBehavior', ctypes.c_ulong)
            # canJoinAllSpaces + fullScreenAuxiliary, without mutually exclusive flags.
            behavior = (behavior & ~(2 | 128)) | 1 | 256
            send(window, b'setCollectionBehavior:', None, (ctypes.c_ulong,), (behavior,))
    except Exception as exc:
        print('Spaces support unavailable:', exc, file=sys.stderr)


def read_pixmap(path):
    # QPixmap(filename) implicitly keeps large source atlases in Qt's global
    # cache. Only the final frames are needed after decoding.
    return QPixmap.fromImage(QImageReader(str(path)).read())


def animation_fingerprint(path, spec):
    digest = hashlib.sha256(b'yun-jin-normalized-v1\0')
    digest.update(json.dumps(spec, sort_keys=True).encode('utf-8'))
    digest.update(path.read_bytes())
    return digest.hexdigest()[:24]


class Frames(Mapping):
    """Original frames plus a bounded cache of two decoded animation clips."""
    def __init__(self):
        self.original = {}
        self.loaders = {}
        self.cache = OrderedDict()

    def __getitem__(self, key):
        row, col = key
        if row < 100:
            return self.original[key]
        count, load = self.loaders[row]
        if not 0 <= col < count:
            raise KeyError(key)
        if row not in self.cache:
            self.cache[row] = load()
            while len(self.cache) > 2:
                self.cache.popitem(last=False)
        self.cache.move_to_end(row)
        return self.cache[row][col]

    def __setitem__(self, key, value):
        self.original[key] = value

    def __iter__(self):
        yield from self.original
        for row, (count, _) in self.loaders.items():
            for col in range(count):
                yield row, col

    def __len__(self):
        return len(self.original) + sum(count for count, _ in self.loaders.values())


class SpriteSheet:
    def __init__(self, path):
        sheet = read_pixmap(path)
        if sheet.isNull():
            raise RuntimeError('Non riesco a leggere spritesheet-yun-jin-v2.png.\n'
                               'Mettilo nella stessa cartella di yun_jin_pet.py.')
        if sheet.width() < 80 or sheet.height() < 110:
            raise RuntimeError('Lo spritesheet è troppo piccolo o non valido.')
        self.ratio = (sheet.height() / 11) / (sheet.width() / 8)
        self.frames = Frames()
        # The supplied 1374 x 2048 sheet has fractional cell boundaries.
        # Round each boundary independently; never crop the character to its bbox.
        for row in range(11):
            for col in range(8):
                x0, x1 = round(col * sheet.width() / 8), round((col + 1) * sheet.width() / 8)
                y0, y1 = round(row * sheet.height() / 11), round((row + 1) * sheet.height() / 11)
                self.frames[row, col] = sheet.copy(x0, y0, x1-x0, y1-y0)
        self.event_animations = {}
        self.load_extra_animations()

    def align_frame(self,cell):
        # Anchoring is technical sprite packing, with no redrawing of artwork.
        def bounds(pix):
            image=pix.toImage()
            xs,ys=[],[]
            for y in range(image.height()):
                for x in range(image.width()):
                    if image.pixelColor(x,y).alpha()>80:
                        xs.append(x);ys.append(y)
            if not xs:
                return None
            return min(xs),min(ys),max(xs)+1,max(ys)+1
        source=bounds(cell)
        if not source:
            return cell
        reference=self.frames[0,5]
        if not hasattr(self,'reference_bounds'):
            self.reference_bounds=bounds(reference)
        x0,y0,x1,y1=source
        rx0,ry0,rx1,ry1=self.reference_bounds
        scale=(ry1-ry0)/(y1-y0)
        scale=min(scale,(reference.width()-4)/(x1-x0))
        cropped=cell.copy(x0,y0,x1-x0,y1-y0)
        target=QPixmap(reference.size())
        target.fill(Qt.GlobalColor.transparent)
        painter=QPainter(target)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        width,height=cropped.width()*scale,cropped.height()*scale
        painter.drawPixmap(QRectF((rx0+rx1-width)/2,ry1-height,width,height),cropped,QRectF(cropped.rect()))
        painter.end()
        return target

    def load_extra_animations(self):
        """Optional arbitrary-length sheets. The original artwork stays untouched."""
        manifest = BASE / 'assets' / 'animations.json'
        if not manifest.is_file():
            return
        try:
            document = json.loads(manifest.read_text(encoding='utf-8'))
            for number, spec in enumerate(document.get('animations', [])):
                name = str(spec['name'])
                if name in BUILTIN_ANIMATIONS:
                    continue
                columns, rows, count = int(spec['columns']), int(spec['rows']), int(spec['count'])
                if min(columns,rows,count)<1 or count>min(columns*rows,512):
                    raise ValueError('Griglia o numero di frame non valido')
                path = (manifest.parent / spec['file']).resolve()
                path.relative_to(manifest.parent.resolve())
                timing = spec.get('seconds_per_frame', .12)
                durations = [float(timing)]*count if isinstance(timing,(int,float)) else [float(t) for t in timing]
                if len(durations)!=count or any(not .02<=t<=10 for t in durations):
                    raise ValueError('Durate fotogrammi non valide')
                key = 100 + number
                order=spec.get('frame_order',list(range(count)))
                if len(order)!=count or any(not isinstance(i,int) or not 0<=i<columns*rows for i in order):
                    raise ValueError('Ordine dei fotogrammi non valido')
                self.frames.loaders[key] = (count, lambda spec=spec, path=path: self.optional_clip(path, spec))
                ANIMATIONS[name] = (key,count,durations)
                LABELS[name] = str(spec.get('label',name))
                if spec.get('event') in ('saved','reminder','speaking','completed','preparing','break','conducting','chronometer'):
                    self.event_animations[spec['event']] = name
        except Exception:
            logging.exception('Optional animation pack could not be loaded')

    def optional_clip(self, path, spec):
        try:
            return self.load_clip(path, spec)
        except Exception:
            logging.exception('Optional animation could not be decoded: %s', path.name)
            return [self.frames[0, i % 6] for i in range(int(spec['count']))]

    def load_clip(self, path, spec, use_cache=True):
        count = int(spec['count'])
        if use_cache:
            normalized = path.parent / 'normalized' / (spec['name'] + '-' + animation_fingerprint(path, spec) + '.png')
            if normalized.is_file():
                pix = read_pixmap(normalized)
                ref = self.frames[0, 5]
                if pix.width() == ref.width()*4 and pix.height() == ref.height()*math.ceil(count/4):
                    return [pix.copy((i%4)*ref.width(), (i//4)*ref.height(), ref.width(), ref.height()) for i in range(count)]
        pix = read_pixmap(path)
        if pix.isNull():
            raise ValueError('Immagine animazione non leggibile: ' + path.name)
        columns, rows = int(spec['columns']), int(spec['rows'])
        order = spec.get('frame_order', list(range(count)))
        cells=[]
        rects=spec.get('frame_rects')
        offsets=spec.get('frame_offsets')
        canvas=spec.get('frame_canvas')
        clip_rows=spec.get('frame_clip_rows')
        if clip_rows is not None and (not rects or len(clip_rows)!=len(rects)):
            raise ValueError('Maschere fotogrammi incomplete')
        if rects is not None:
            if len(rects)!=columns*rows or len(offsets or [])!=len(rects) or not canvas or len(canvas)!=2:
                raise ValueError('Ritagli o ancoraggi incompleti')
            if any(not isinstance(v,int) or not 1<=v<=4096 for v in canvas):
                raise ValueError('Dimensioni canvas non valide')
        for source_index in order:
            c,r = source_index%columns,source_index//columns
            x0,x1 = round(c*pix.width()/columns),round((c+1)*pix.width()/columns)
            y0,y1 = round(r*pix.height()/rows),round((r+1)*pix.height()/rows)
            cell=pix.copy(x0,y0,x1-x0,y1-y0)
            if rects is not None:
                x,y,w,h=rects[source_index]
                if min(x,y)<0 or min(w,h)<1 or x+w>pix.width() or y+h>pix.height():
                    raise ValueError('Ritaglio fuori tavola')
                cell=QPixmap(*canvas);cell.fill(Qt.GlobalColor.transparent)
                painter=QPainter(cell)
                if clip_rows is not None:
                    region=QRegion()
                    ox,oy=offsets[source_index]
                    for row,left,length in clip_rows[source_index]:
                        if min(row,left)<0 or length<1 or row>=h or left+length>w:
                            raise ValueError('Maschera fuori fotogramma')
                        region=region.united(QRegion(QRect(ox+left,oy+row,length,1)))
                    painter.setClipRegion(region)
                painter.drawPixmap(QPoint(*offsets[source_index]),pix.copy(x,y,w,h))
                painter.end()
            cells.append(cell)
        if spec.get('align_as_sequence',False):
            cells=self.align_sequence(cells,spec)
        if spec.get('align_to_original', False) and not spec.get('align_as_sequence', False):
            cells = [self.align_frame(cell) for cell in cells]
        return cells

    def align_sequence(self,cells,spec=None):
        """One fixed transform per clip; preserve pose proportions and movement."""
        bounds=[]
        for cell in cells:
            rect=QRegion(cell.mask()).boundingRect()
            if not rect.isEmpty():
                bounds.append((rect.left(),rect.top(),rect.right()+1,rect.bottom()+1))
        if not bounds:
            return cells
        x0=min(b[0] for b in bounds);y0=min(b[1] for b in bounds)
        x1=max(b[2] for b in bounds);y1=max(b[3] for b in bounds)
        ref=self.frames[0,5]
        if spec and spec.get('sequence_body_height'):
            reference=ref.toImage()
            opaque=[(x,y) for y in range(reference.height()) for x in range(reference.width())
                    if reference.pixelColor(x,y).alpha()>80]
            left=min(x for x,y in opaque);top=min(y for x,y in opaque)
            right=max(x for x,y in opaque)+1;bottom=max(y for x,y in opaque)+1
            ref_bounds=QRect(left,top,right-left,bottom-top)
            center=float(spec['sequence_center']);ground=float(spec['sequence_ground'])
            height=float(spec['sequence_body_height'])
            if height<=0 or not x0<center<x1 or ground<=y0:
                raise ValueError('Ancoraggio sequenza non valido')
            rx=ref_bounds.center().x();ry=ref_bounds.bottom()+1
            # One ISOTROPIC scale for the whole clip: never squeeze the artwork
            # horizontally to compensate for differences in generated anatomy.
            scale=min(ref_bounds.height()/height,
                      (rx-2)/max(1,center-x0),
                      (ref.width()-2-rx)/max(1,x1-center),
                      (ry-2)/max(1,ground-y0))
            if y1>ground:scale=min(scale,(ref.height()-2-ry)/(y1-ground))
            dx=rx-center*scale;dy=ry-ground*scale
        else:
            scale=min((ref.width()-4)/(x1-x0),(ref.height()-4)/(y1-y0))
            dx=(ref.width()-(x1-x0)*scale)/2-x0*scale
            dy=ref.height()-2-y1*scale
        result=[]
        for cell in cells:
            target=QPixmap(ref.size());target.fill(Qt.GlobalColor.transparent)
            painter=QPainter(target)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(QRectF(dx,dy,cell.width()*scale,cell.height()*scale),cell,QRectF(cell.rect()))
            painter.end();result.append(target)
        return result


class YunJinPet(QWidget):
    def __init__(self, settings=None):
        super().__init__()
        self.sheet = SpriteSheet(BASE / 'spritesheet-yun-jin-v2.png')
        self.settings = settings or QSettings('YunJinPet', 'DesktopCompanion')
        self.setWindowTitle('Yun Jin')
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        if sys.platform == 'darwin':
            flags |= Qt.WindowType.Tool  # Qt creates an NSPanel for fullscreen overlays.
            self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setWindowIcon(QIcon(self.sheet.frames[0, 0]))
        self.setToolTip('Doppio clic: pannello · Clic destro: menu')
        self.mode = self.settings.value('mode', 'normal')
        if self.mode not in ('normal', 'lively', 'quiet', 'asleep'):
            self.mode = 'normal'
        self.allow_walk = self.settings.value('walk', True, type=bool)
        self.allow_gaze = self.settings.value('gaze', True, type=bool)
        self.pet_width = max(80, min(260, self.settings.value('size', 130, type=int)))
        self.setFixedSize(self.pet_width, round(self.pet_width * self.sheet.ratio))
        self.setWindowOpacity(max(.35, min(1., self.settings.value('opacity', 1., type=float))))
        self.action_serial = 0
        self.state = 'idle'
        self.animation = 'idle'
        self.frame = 0
        self.frame_elapsed = 0.0
        self.loops = 0
        self.queue = deque()
        self.locked = False
        self.paused = False
        self.menu_open = False
        self.target = None
        self.follow_until = 0.0
        self.following = False
        self.sleep_cycles = None
        self.sleep_after = None
        self.wake_requested = False
        self.next_sleep = time.monotonic() + random.uniform(600, 1200)
        self.arrival = None
        self.look = None
        self.previous_action = None
        self.drag_anchor = None
        self.dragged = False
        self.suppress_release = False
        self.cursor = QCursor.pos()
        self.last_cursor_motion = time.monotonic()
        self.away = False
        self.next_blink = time.monotonic() + random.uniform(3, 6)
        self.blink_until = 0.0
        self.next_decision = time.monotonic() + 5
        self.last_tick = time.monotonic()
        self.click_timer = QTimer(self)
        self.click_timer.setSingleShot(True)
        self.click_timer.timeout.connect(self.greet)
        self.call_timer = QTimer(self)
        self.call_timer.setSingleShot(True)
        self.call_timer.timeout.connect(self.begin_follow)
        screen = QApplication.primaryScreen()
        rect = screen.availableGeometry()
        default = QPoint(rect.right() - self.width() - 32, rect.bottom() - self.height() - 16)
        saved = self.settings.value('position', default, type=QPoint)
        self.xy = QPointF(saved)
        self.move(saved)
        self.ensure_visible()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(33)
        app = QApplication.instance()
        app.screenAdded.connect(self.connect_screen)
        app.screenRemoved.connect(lambda _: QTimer.singleShot(0, self.ensure_visible))
        for screen in app.screens():
            self.connect_screen(screen)
        self.sequence([('wave', 1)])

    def greet(self):
        self.sequence([('wave', 1)])

    def add_companion_menu(self, menu):
        pass

    def connect_screen(self, screen):
        screen.availableGeometryChanged.connect(lambda _: self.ensure_visible())

    def current_screen(self):
        return QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()

    def ensure_visible(self):
        screen = self.current_screen()
        # Oversized pets still fit low-resolution screens.
        rect = screen.availableGeometry()
        self.xy = clamp_to_screen(QPointF(self.pos()), rect, self.width(), self.height())
        self.move(self.xy.toPoint())
        if self.target is not None:
            self.target = clamp_to_screen(self.target, rect, self.width(), self.height())

    def play(self, name):
        self.animation = name
        self.frame = 0
        self.frame_elapsed = 0.
        self.look = None
        self.update()

    def cancel(self):
        self.action_serial += 1
        self.click_timer.stop()
        self.call_timer.stop()
        self.queue.clear()
        self.target = None
        self.following = False
        self.follow_until = 0.
        self.sleep_after = None
        self.wake_requested = False
        self.arrival = None
        self.locked = False
        self.look = None
        self.state = 'idle'
        self.play('idle')

    def idle(self):
        self.state = 'idle'
        self.target = None
        self.following = False
        self.play('idle')
        self.next_decision = time.monotonic() + random.uniform(5, 10)
        if self.mode == 'asleep':
            self.next_decision = time.monotonic() + 1

    def is_sleeping(self):
        return self.state in ('sleep_enter', 'sleep_loop', 'sleep_exit')

    def start_sleep(self, cycles=None):
        if not all(name in ANIMATIONS for name in SLEEP_ANIMATIONS):
            return False
        self.cancel()
        self.paused = False
        self.sleep_cycles = cycles
        self.state = 'sleep_enter'
        self.play('sleep_in')
        return True

    def wake_up(self, after=None, leave_mode=False):
        if leave_mode and self.mode == 'asleep':
            self.mode = 'normal'
            self.save_settings()
        if not self.is_sleeping():
            if after:
                after()
            return
        self.sleep_after = after
        self.wake_requested = True
        self.paused = False
        # Finish lowering herself before reversing the seated pose. Never cut
        # between unrelated standing/seated frames midway through a transition.
        if self.state == 'sleep_loop':
            self.state = 'sleep_exit'
            self.play('sleep_out')

    def next_sleep_phase(self):
        if self.state == 'sleep_enter':
            self.state = 'sleep_exit' if self.wake_requested else 'sleep_loop'
            self.play('sleep_out' if self.wake_requested else 'sleep_loop')
        elif self.state == 'sleep_loop':
            if self.sleep_cycles is not None:
                self.sleep_cycles -= 1
                if self.sleep_cycles <= 0:
                    self.wake_up()
        elif self.state == 'sleep_exit':
            after = self.sleep_after
            self.sleep_after = None
            self.wake_requested = False
            self.next_sleep = time.monotonic() + random.uniform(900, 1800)
            self.idle()
            if after:
                after()

    def sequence(self, steps):
        """(animation, complete cycles), with no delayed callbacks from old actions."""
        if self.is_sleeping():
            steps = list(steps)
            self.wake_up(lambda: self.sequence(steps), leave_mode=True)
            return
        self.cancel()
        self.paused = False
        self.queue.extend(steps)
        self.next_step()

    def next_step(self):
        if not self.queue:
            self.idle()
            return
        name, self.loops = self.queue.popleft()
        self.state = 'action'
        self.play(name)

    def hold_pose(self, name):
        if self.is_sleeping():
            self.wake_up(lambda: self.hold_pose(name), leave_mode=True)
            return
        self.paused = False
        self.cancel()
        self.locked = True
        self.state = 'pose'
        self.play(name)

    def animate(self, dt):
        self.frame_elapsed += dt
        durations = ANIMATIONS[self.animation][2]
        while self.frame_elapsed >= durations[self.frame]:
            self.frame_elapsed -= durations[self.frame]
            self.frame += 1
            if self.frame == len(durations):
                self.frame = 0
                if self.is_sleeping():
                    self.next_sleep_phase()
                    break
                if self.state == 'action':
                    self.loops -= 1
                    if self.loops <= 0:
                        self.next_step()
                        break
        self.update_frame()

    def tick(self):
        now = time.monotonic()
        dt = min(.1, now - self.last_tick)
        self.last_tick = now
        if self.menu_open or self.paused or self.drag_anchor is not None:
            return
        cursor = QCursor.pos()
        if cursor != self.cursor:
            self.last_cursor_motion = now
            self.cursor = cursor
            if self.away and not self.locked and self.state == 'idle':
                self.away = False
                self.sequence([('wave', 1)])
        if self.state == 'move':
            self.move_step(dt, now)
        elif self.state == 'idle' and now >= self.next_decision:
            self.decide(now)
        self.animate(dt)
        self.look = None
        if (self.state == 'idle' and self.allow_gaze and not self.locked
                and now - self.last_cursor_motion < 5):
            head = self.pos() + QPoint(self.width() // 2, round(self.height() * .27))
            dx, dy = cursor.x()-head.x(), cursor.y()-head.y()
            if 18 < math.hypot(dx, dy) < 650:
                self.look = gaze_index(dx, dy)
                if now >= self.next_blink:
                    self.blink_until = now + .13
                    self.next_blink = now + random.uniform(3, 6)
        if self.state == 'gaze_demo':
            self.look = int(now * 2) % 16
        self.update_frame()

    def decide(self, now):
        if self.mode == 'asleep':
            if not self.start_sleep():
                self.next_decision = now + 10
            return
        if getattr(self, 'use_extra_animations', True) and now >= self.next_sleep and random.random() < .025:
            if self.start_sleep(random.randint(5, 10)):
                return
        if now - self.last_cursor_motion > 90:
            self.away = True
            self.sequence([('wait', 2), ('idle', 4)])
            return
        choices = ['idle', 'wave', 'review', 'work', 'combo', 'wait', 'walk', 'follow', 'failed']
        weights = ([24, 12, 12, 15, 12, 8, 12, 4, 1] if self.mode == 'lively' else
                   [37, 10, 12, 12, 7, 10, 9, 2, 1])
        if self.mode == 'quiet':
            weights = [55, 3, 17, 18, 0, 7, 0, 0, 0]
        if not self.allow_walk:
            weights[6] = weights[7] = 0
        if self.previous_action in choices and self.previous_action != 'idle':
            weights[choices.index(self.previous_action)] = 0
        action = random.choices(choices, weights)[0]
        self.previous_action = action
        if action == 'walk':
            self.wander()
        elif action == 'follow':
            self.begin_follow()
        elif action == 'combo':
            self.sequence([('idle', 1), ('jump', 1), ('idle', 1), ('wave', 1)])
        elif action == 'work':
            self.sequence([('review', 1), ('work', random.randint(2, 3)), ('wave', 1)])
        elif action == 'failed':
            self.sequence([('failed', 1), ('idle', 1), ('wave', 1)])
        elif action == 'idle':
            self.next_decision = now + random.uniform(6, 12)
        else:
            self.sequence([(action, random.randint(1, 2))])

    def start_move(self, point, arrival='review'):
        if self.is_sleeping():
            self.wake_up(lambda: self.start_move(point, arrival), leave_mode=True)
            return
        self.paused = False
        self.cancel()
        rect = self.current_screen().availableGeometry()
        self.xy = QPointF(self.pos())
        self.target = clamp_to_screen(QPointF(point), rect, self.width(), self.height())
        self.arrival = arrival
        self.state = 'move'
        self.play('left' if self.target.x() < self.xy.x() else 'right')

    def wander(self):
        rect = self.current_screen().availableGeometry()
        # Short excursions are less distracting than repeatedly crossing the desktop.
        point = QPointF(self.x() + random.uniform(-330, 330), self.y() + random.uniform(-190, 190))
        point = clamp_to_screen(point, rect, self.width(), self.height())
        self.start_move(point, random.choice(['review', 'wave', 'wait']))

    def cursor_target(self):
        rect = self.current_screen().availableGeometry()
        cursor = QCursor.pos()
        # Stay on the current monitor; dragging / menu moves her to another one.
        if not rect.contains(cursor):
            return None
        center = QPointF(self.geometry().center())
        dx, dy = center.x()-cursor.x(), center.y()-cursor.y()
        dist = math.hypot(dx, dy)
        stop = self.width() * .65 + 35
        if dist < stop + 8:
            return QPointF(self.pos())
        point = QPointF(cursor.x() + dx/dist*stop - self.width()/2,
                        cursor.y() + dy/dist*stop - self.height()/2)
        return clamp_to_screen(point, rect, self.width(), self.height())

    def begin_follow(self):
        point = self.cursor_target()
        self.start_move(point if point is not None else QPointF(self.pos()), 'wave')
        self.following = True
        self.follow_until = time.monotonic() + 9

    def call_later(self):
        if self.is_sleeping():
            self.wake_up(self.call_later, leave_mode=True)
            return
        if self.mode == 'asleep':
            self.mode = 'normal'
            self.save_settings()
        self.cancel()
        self.paused = False
        # The two seconds let the user move away from the menu. This is an
        # explicit state: an expired idle decision must not cancel this timer.
        self.state = 'follow_pending'
        self.call_timer.start(2000)

    def move_step(self, dt, now):
        if self.following:
            if now >= self.follow_until:
                self.sequence([('wave', 1)])
                return
            point = self.cursor_target()
            if point is None:
                # Wait on this monitor; resume if the pointer comes back.
                self.target = QPointF(self.pos())
            else:
                self.target = point
        if self.target is None:
            self.idle()
            return
        dx, dy = self.target.x()-self.xy.x(), self.target.y()-self.xy.y()
        distance = math.hypot(dx, dy)
        speed = (125 if self.mode == 'lively' else 90) * self.width()/130
        step = speed * dt
        if distance <= max(2, step):
            self.xy = QPointF(self.target)
            self.move(self.xy.toPoint())
            if self.following:
                if self.animation != 'wait':
                    self.play('wait')
            else:
                self.sequence([(self.arrival or 'review', 1)])
            return
        direction = 'left' if dx < 0 else 'right'
        if direction != self.animation:
            self.play(direction)
        self.xy += QPointF(dx/distance*step, dy/distance*step)
        self.move(self.xy.toPoint())

    def visible_frame(self):
        row = ANIMATIONS[self.animation][0]
        col = self.frame
        if self.look is not None:
            row, col = 9 + self.look // 8, self.look % 8
            if self.state != 'gaze_demo' and time.monotonic() < self.blink_until:
                row, col = 0, 1
        return row, col

    def update_frame(self):
        key = self.visible_frame()
        if key != getattr(self, '_painted_frame', None):
            self.update()

    def paintEvent(self, event):
        row, col = self.visible_frame()
        self._painted_frame = (row, col)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        pix = self.sheet.frames[row, col]
        target = QRectF(self.rect())
        if row >= 100:
            size = pix.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            target = QRectF((self.width()-size.width())/2, self.height()-size.height(),size.width(),size.height())
        painter.drawPixmap(target, pix, QRectF(pix.rect()))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.click_timer.stop()
            if self.is_sleeping():
                self.wake_up(leave_mode=True)
            else:
                self.cancel()
            self.drag_anchor = event.globalPosition().toPoint() - self.pos()
            self.press_point = event.globalPosition().toPoint()
            self.dragged = False

    def mouseMoveEvent(self, event):
        if self.drag_anchor is None:
            return
        point = event.globalPosition().toPoint()
        if (point - self.press_point).manhattanLength() >= QApplication.startDragDistance():
            self.dragged = True
        if self.dragged:
            self.xy = QPointF(point - self.drag_anchor)
            self.move(self.xy.toPoint())
            if not self.is_sleeping() and self.animation != 'wait':
                self.play('wait')

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.drag_anchor = None
        self.ensure_visible()
        if self.suppress_release:
            self.suppress_release = False
        elif self.dragged:
            self.sequence([('jump', 1), ('wave', 1)])
            self.save_settings()
        else:
            self.click_timer.start(QApplication.doubleClickInterval())

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_anchor = None
            self.suppress_release = True
            self.open_panel()

    def set_mode(self, mode):
        if mode not in ('asleep', 'quiet', 'normal', 'lively'):
            return
        self.mode = mode
        if mode == 'asleep':
            if not self.is_sleeping():
                self.start_sleep()
            else:
                self.sleep_cycles = None
                self.sleep_after = None
        elif self.is_sleeping():
            self.wake_up()
        else:
            self.cancel()
        self.save_settings()

    def set_size(self, size):
        feet = self.geometry().bottomLeft() + QPoint(self.width() // 2, 0)
        self.pet_width = size
        self.setFixedSize(size, round(size * self.sheet.ratio))
        self.move(feet.x()-size//2, feet.y()-self.height()+1)
        self.ensure_visible()
        self.save_settings()

    def set_paused(self, value):
        self.paused = value
        self.cancel()
        self.last_tick = time.monotonic()

    def set_walk(self, value):
        self.allow_walk = value
        if not value and self.state == 'move':
            self.cancel()
        self.save_settings()

    def set_gaze(self, value):
        self.allow_gaze = value
        self.save_settings()

    def set_opacity(self, value):
        self.setWindowOpacity(value)
        self.save_settings()

    def gaze_demo(self):
        self.paused = False
        self.cancel()
        self.locked = True
        self.state = 'gaze_demo'

    def move_to_screen(self, screen):
        self.cancel()
        rect = screen.availableGeometry()
        self.move(rect.center() - QPoint(self.width()//2, self.height()//2))
        self.ensure_visible()
        self.save_settings()

    def performance(self):
        self.sequence([('review', 1), ('work', 2), ('jump', 1), ('wave', 2)])

    def populate_context_menu(self, menu):
        from yun_jin_ui import STYLE
        menu.setStyleSheet(STYLE)
        menu.clear()
        self.add_companion_menu(menu)
        menu.addSeparator()
        behavior = menu.addMenu('Comportamento')
        behavior.addAction('Riprendi', self.resume)
        pause = behavior.addAction('Pausa completa')
        pause.setCheckable(True)
        pause.setChecked(self.paused)
        pause.triggered.connect(self.set_paused)
        behavior.addAction('Seguimi', self.call_later)
        behavior.addAction('Passeggia', self.wander)
        behavior.addAction('Esibizione', self.performance)
        modes = behavior.addMenu('Carattere')
        group = QActionGroup(modes)
        for key, label in [('asleep', 'Addormentata'), ('quiet', 'Tranquilla'), ('normal', 'Normale'), ('lively', 'Vivace')]:
            action = modes.addAction(label)
            action.setCheckable(True)
            action.setChecked(self.mode == key)
            group.addAction(action)
            action.triggered.connect(lambda checked, k=key: self.set_mode(k))
        for label, value, callback in [('Passeggiate spontanee', self.allow_walk, self.set_walk),
                                       ('Sguardo sul cursore', self.allow_gaze, self.set_gaze)]:
            action = behavior.addAction(label)
            action.setCheckable(True)
            action.setChecked(value)
            action.triggered.connect(callback)
        animations = menu.addMenu('Animazioni')
        self.populate_animation_groups(animations)
        animations.addSeparator()
        self.populate_animation_groups(animations.addMenu('Ripeti'), repeat=True)
        stop = animations.addAction('Termina', self.resume)
        stop.setEnabled(self.state not in ('idle', 'walk', 'follow', 'follow_pending'))
        appearance = menu.addMenu('Aspetto')
        sizes = appearance.addMenu('Dimensioni')
        size_group = QActionGroup(sizes)
        for size in [100, 130, 160, 190, 230]:
            action = sizes.addAction(f'{size} px' + ('' if size == 130 else ''))
            action.setCheckable(True)
            action.setChecked(self.width() == size)
            size_group.addAction(action)
            action.triggered.connect(lambda checked, s=size: self.set_size(s))
        opacity = appearance.addMenu('Opacità')
        for value in [1., .85, .65, .45]:
            opacity.addAction(f'{round(value*100)}%', lambda checked=False, v=value: self.set_opacity(v))
        screens = appearance.addMenu('Monitor')
        for i, screen in enumerate(QApplication.screens(), 1):
            screens.addAction(f'{i} · {screen.name()}', lambda checked=False, s=screen: self.move_to_screen(s))
        appearance.addAction('Riporta sullo schermo', self.ensure_visible)
        self.add_companion_footer(menu)
        menu.addSeparator()
        menu.addAction('Chiudi', self.close)

    def populate_animation_groups(self, menu, repeat=False):
        for title, names in ANIMATION_GROUPS:
            available = [name for name in names if name in ANIMATIONS]
            if not available: continue
            group = menu.addMenu(title)
            for name in available:
                group.addAction(LABELS[name], lambda checked=False, n=name, r=repeat:
                                self.hold_pose(n) if r else self.sequence([(n, 1)]))
            if title == 'Riposo':
                if repeat:
                    group.addAction('Sonno', lambda: self.set_mode('asleep'))
                    group.addAction('Direzioni dello sguardo', self.gaze_demo)
                else:
                    group.addAction('Sonnellino', lambda: self.start_sleep(6))
            if title == 'Movimento' and not repeat:
                group.addAction('Riposo → salto → riposo',
                                lambda: self.sequence([('idle', 1), ('jump', 1), ('idle', 1)]))

    def add_companion_footer(self, menu):
        pass

    def contextMenuEvent(self, event):
        self.click_timer.stop()
        # Ctrl-click on macOS can begin a left-button drag before opening
        # the context menu; the corresponding release may go to the popup.
        self.drag_anchor = None
        self.dragged = False
        self.menu_open = True
        opened = time.monotonic()
        menu = QMenu(self)
        self.populate_context_menu(menu)
        def resume_after_menu():
            if self.menu_open:
                self.follow_until += time.monotonic() - opened
                self.last_tick = time.monotonic()
                self.menu_open = False
        # exec() may not return until an action's modal dialog closes.
        # Resume when the popup actually hides, before that dialog opens.
        menu.aboutToHide.connect(resume_after_menu)
        try:
            menu.exec(event.globalPos())
        finally:
            resume_after_menu()
            menu.deleteLater()

    def open_panel(self):
        self.sequence([('jump', 1), ('wave', 2), ('jump', 1)])

    def resume(self):
        if self.is_sleeping():
            self.wake_up(leave_mode=True)
            return
        if self.mode == 'asleep':
            self.mode = 'normal'
            self.save_settings()
        self.paused = False
        self.cancel()
        self.next_decision = time.monotonic() + 5

    def save_settings(self):
        for key, value in [('position', self.pos()), ('size', self.width()), ('mode', self.mode),
                           ('walk', self.allow_walk), ('gaze', self.allow_gaze), ('opacity', self.windowOpacity())]:
            self.settings.setValue(key, value)
        self.settings.sync()

    def closeEvent(self, event):
        self.save_settings()
        self.timer.stop()
        event.accept()


def main():
    from yun_jin_windows import set_process_identity, install_taskbar_icons
    set_process_identity()
    app = QApplication(sys.argv)
    install_taskbar_icons(app, BASE/'favicon.ico')
    app.setApplicationName('Yun Jin')
    # Avoid accidentally launching a second pet by double-clicking again.
    tag = hashlib.sha256(str(BASE).encode()).hexdigest()[:16]
    lock = QLockFile(str(Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation)) / f'yun-jin-{tag}.lock'))
    lock.setStaleLockTime(0)
    if not lock.tryLock(50):
        return 0
    try:
        pet = YunJinPet()
    except Exception as exc:
        from yun_jin_dialogs import Messages
        Messages.critical(None, 'Yun Jin · avvio non riuscito', str(exc))
        return 1
    pet.show()
    mac_all_spaces(pet)
    app.aboutToQuit.connect(pet.save_settings)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
