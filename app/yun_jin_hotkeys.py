# SPDX-License-Identifier: GPL-3.0-or-later
"""Configurable native global hotkeys, no keyboard polling or event tap."""
import ctypes
import logging
import sys
from PyQt6.QtCore import Qt, QTimer, QAbstractNativeEventFilter
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication, QDialog, QWidget, QVBoxLayout, QGridLayout, QKeySequenceEdit, QDialogButtonBox, QTabWidget, QLineEdit
from yun_jin_ui import STYLE, plain_label, icon_button, scroll_page

ACTIONS={'panel':'Pannello','reminder':'Nuovo promemoria','read':'Leggi testo copiato',
         'stop':'Interrompi voce','study':'Studio',
         'stopwatch_toggle':'Cronometro · Avvia / Pausa','stopwatch_lap':'Cronometro · Parziale',
         'stopwatch_reset':'Cronometro · Azzera','stopwatch_open':'Apri cronometro',
         'metronome_toggle':'Metronomo · Avvia / Ferma','metronome_open':'Apri metronomo',
         'focus_toggle':'Focus · Avvia / Interrompi','focus_open':'Apri focus',
         'note':'Nuovo appunto','capture':'Importa appunti copiati',
         'pet_pause':'Pausa / Riprendi Yun Jin','quiet':'Silenzio per un’ora / Riattiva',
         'pet_visibility':'Mostra / Nascondi Yun Jin'}
GROUPS=(('Generali',('panel','note','capture','reminder','study','pet_pause','pet_visibility')),
        ('Voce',('read','stop','quiet')),
        ('Cronometro',('stopwatch_toggle','stopwatch_lap','stopwatch_reset','stopwatch_open')),
        ('Metronomo',('metronome_toggle','metronome_open')),('Focus',('focus_toggle','focus_open')))
LEGACY_DEFAULTS=dict(panel='Ctrl+Alt+J',reminder='Ctrl+Alt+R',read='Ctrl+Alt+L',stop='Ctrl+Alt+S',study='Ctrl+Alt+D')
DEFAULTS={**dict.fromkeys(ACTIONS,''),**LEGACY_DEFAULTS,'study':'Ctrl+Alt+Shift+D' if sys.platform=='darwin' else 'Ctrl+Alt+D'}
IDENTS={name:0x5911+i for i,name in enumerate(ACTIONS)}


def normalize(value, platform=None):
    platform=sys.platform if platform is None else platform
    seq=QKeySequence(value,QKeySequence.SequenceFormat.PortableText)
    if not value or seq.isEmpty():
        if value: raise ValueError('Combinazione non valida.')
        return ''
    if seq.count()!=1: raise ValueError('Usa una sola combinazione di tasti.')
    combination=seq[0]; key=int(combination.key()); mods=combination.keyboardModifiers()
    if not mods & (Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.AltModifier|Qt.KeyboardModifier.MetaModifier):
        raise ValueError('Aggiungi Ctrl, Alt oppure '+('⌘.' if platform=='darwin' else 'Win.'))
    special={int(k) for k in (Qt.Key.Key_Space,Qt.Key.Key_Home,Qt.Key.Key_End,Qt.Key.Key_PageUp,Qt.Key.Key_PageDown,
                             Qt.Key.Key_Left,Qt.Key.Key_Right,Qt.Key.Key_Up,Qt.Key.Key_Down)}
    if not (ord('A')<=key<=ord('Z') or ord('0')<=key<=ord('9') or
            int(Qt.Key.Key_F1)<=key<=int(Qt.Key.Key_F20) or key in special):
        raise ValueError('Usa una lettera, un numero, un tasto F1–F20, spazio o una freccia.')
    if platform=='win32' and key==int(Qt.Key.Key_F12): raise ValueError('F12 è riservato da Windows.')
    return seq.toString(QKeySequence.SequenceFormat.PortableText)


def native_modifiers(sequence, platform):
    mods=QKeySequence(sequence)[0].keyboardModifiers()
    mapping = ((Qt.KeyboardModifier.ControlModifier,256),(Qt.KeyboardModifier.MetaModifier,4096),
               (Qt.KeyboardModifier.AltModifier,2048),(Qt.KeyboardModifier.ShiftModifier,512)) if platform=='darwin' else (
               (Qt.KeyboardModifier.ControlModifier,2),(Qt.KeyboardModifier.MetaModifier,8),
               (Qt.KeyboardModifier.AltModifier,1),(Qt.KeyboardModifier.ShiftModifier,4))
    return sum(value for flag,value in mapping if mods&flag)


class WindowsBackend(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__(); self.callback=callback; self.registered=set()
        from ctypes import wintypes
        self.MSG=wintypes.MSG
        self.user=ctypes.WinDLL('user32',use_last_error=True)
        self.user.RegisterHotKey.argtypes=[wintypes.HWND,ctypes.c_int,wintypes.UINT,wintypes.UINT]
        self.user.RegisterHotKey.restype=wintypes.BOOL
        self.user.UnregisterHotKey.argtypes=[wintypes.HWND,ctypes.c_int]
        self.user.UnregisterHotKey.restype=wintypes.BOOL
        QApplication.instance().installNativeEventFilter(self)

    def register(self,ident,sequence):
        key=int(QKeySequence(sequence)[0].key())
        special={Qt.Key.Key_Space:32,Qt.Key.Key_Home:36,Qt.Key.Key_End:35,Qt.Key.Key_PageUp:33,
                 Qt.Key.Key_PageDown:34,Qt.Key.Key_Left:37,Qt.Key.Key_Right:39,Qt.Key.Key_Up:38,Qt.Key.Key_Down:40}
        vk=special.get(key,key)
        if int(Qt.Key.Key_F1)<=key<=int(Qt.Key.Key_F20): vk=112+key-int(Qt.Key.Key_F1)
        if not self.user.RegisterHotKey(None,ident,native_modifiers(sequence,'win32')|0x4000,vk): return False
        self.registered.add(ident);return True

    def unregister_all(self):
        for ident in self.registered: self.user.UnregisterHotKey(None,ident)
        self.registered.clear()

    def nativeEventFilter(self,event_type,message):
        if bytes(event_type) in (b'windows_generic_MSG',b'windows_dispatcher_MSG'):
            msg=self.MSG.from_address(int(message))
            if msg.message==0x0312 and int(msg.wParam) in self.registered:
                self.callback(int(msg.wParam));return True,0
        return False,0

    def close(self):
        self.unregister_all();QApplication.instance().removeNativeEventFilter(self)


class MacBackend:
    # CarbonEvents.h: these are Carbon event kinds, not NSEvent subtypes 6/9.
    HOTKEY_PRESSED=5
    HOTKEY_RELEASED=6
    EXCLUSIVE=1
    class Spec(ctypes.Structure):
        _fields_=[('eventClass',ctypes.c_uint32),('eventKind',ctypes.c_uint32)]
    class ID(ctypes.Structure):
        _fields_=[('signature',ctypes.c_uint32),('id',ctypes.c_uint32)]
    SIGNATURE=0x594a494e
    SPECIAL={Qt.Key.Key_Space:49,Qt.Key.Key_Home:115,Qt.Key.Key_End:119,Qt.Key.Key_PageUp:116,
             Qt.Key.Key_PageDown:121,Qt.Key.Key_Left:123,Qt.Key.Key_Right:124,Qt.Key.Key_Up:126,Qt.Key.Key_Down:125}
    FUNCTION=(122,120,99,118,96,97,98,100,101,109,103,111,105,107,113,106,64,79,80,90)

    def __init__(self,callback):
        self.callback=callback;self.registered={};self.pressed=set();self._reserved=None
        self.carbon=ctypes.CDLL('/System/Library/Frameworks/Carbon.framework/Carbon')
        c=self.carbon;p=ctypes.c_void_p;u=ctypes.c_uint32;i=ctypes.c_int32
        self.Handler=ctypes.CFUNCTYPE(i,p,p,p)
        c.GetApplicationEventTarget.argtypes=[];c.GetApplicationEventTarget.restype=p
        c.InstallEventHandler.argtypes=[p,self.Handler,u,ctypes.POINTER(self.Spec),p,ctypes.POINTER(p)]
        c.InstallEventHandler.restype=i
        c.RemoveEventHandler.argtypes=[p];c.RemoveEventHandler.restype=i
        c.RegisterEventHotKey.argtypes=[u,u,self.ID,p,u,ctypes.POINTER(p)];c.RegisterEventHotKey.restype=i
        c.UnregisterEventHotKey.argtypes=[p];c.UnregisterEventHotKey.restype=i
        c.GetEventParameter.argtypes=[p,u,u,p,u,p,p];c.GetEventParameter.restype=i
        c.GetEventKind.argtypes=[p];c.GetEventKind.restype=u
        self.handler=self.Handler(self.handle);self.handler_ref=p()
        specs=(self.Spec*2)(self.Spec(0x6b657962,self.HOTKEY_PRESSED),self.Spec(0x6b657962,self.HOTKEY_RELEASED))
        if c.InstallEventHandler(c.GetApplicationEventTarget(),self.handler,2,specs,None,ctypes.byref(self.handler_ref)):
            raise OSError('Scorciatoie globali macOS non disponibili.')

    def keycode(self,key):
        if key in self.SPECIAL: return self.SPECIAL[key]
        if int(Qt.Key.Key_F1)<=key<=int(Qt.Key.Key_F20): return self.FUNCTION[key-int(Qt.Key.Key_F1)]
        # Translate the current keyboard layout instead of assuming US/QWERTY.
        c=self.carbon;p=ctypes.c_void_p;u=ctypes.c_uint32;short=ctypes.c_uint16
        cf=ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        c.TISCopyCurrentKeyboardLayoutInputSource.argtypes=[];c.TISCopyCurrentKeyboardLayoutInputSource.restype=p
        c.TISGetInputSourceProperty.argtypes=[p,p];c.TISGetInputSourceProperty.restype=p
        cf.CFDataGetBytePtr.argtypes=[p];cf.CFDataGetBytePtr.restype=p
        cf.CFRelease.argtypes=[p];cf.CFRelease.restype=None
        c.LMGetKbdType.argtypes=[];c.LMGetKbdType.restype=ctypes.c_uint8
        c.UCKeyTranslate.argtypes=[p,short,short,u,u,u,ctypes.POINTER(u),u,ctypes.POINTER(u),ctypes.POINTER(short)]
        c.UCKeyTranslate.restype=ctypes.c_int32
        source=c.TISCopyCurrentKeyboardLayoutInputSource()
        try:
            prop=p.in_dll(c,'kTISPropertyUnicodeKeyLayoutData')
            data=c.TISGetInputSourceProperty(source,prop)
            if not data: raise ValueError('Layout tastiera non disponibile.')
            layout=cf.CFDataGetBytePtr(data)
            keypad={65,67,69,71,75,76,78,81,82,83,84,85,86,87,88,89,91,92}
            for modifier in (0,2):
                for code in range(128):
                    if code in keypad:continue
                    dead=u();length=u();chars=(short*4)()
                    error=c.UCKeyTranslate(layout,code,3,modifier,c.LMGetKbdType(),1,ctypes.byref(dead),4,ctypes.byref(length),chars)
                    if not error and length.value==1 and chr(chars[0]).upper()==chr(key): return code

        finally:
            if source: cf.CFRelease(source)
        raise ValueError('Questo tasto non è disponibile nel layout corrente.')

    def system_shortcuts(self):
        """Ask macOS before RegisterEventHotKey, which can accept system conflicts."""
        if self._reserved is not None:return self._reserved
        c=self.carbon;p=ctypes.c_void_p;index=ctypes.c_ssize_t
        cf=ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        c.CopySymbolicHotKeys.argtypes=[ctypes.POINTER(p)];c.CopySymbolicHotKeys.restype=ctypes.c_int32
        cf.CFArrayGetCount.argtypes=[p];cf.CFArrayGetCount.restype=index
        cf.CFArrayGetValueAtIndex.argtypes=[p,index];cf.CFArrayGetValueAtIndex.restype=p
        cf.CFDictionaryGetValue.argtypes=[p,p];cf.CFDictionaryGetValue.restype=p
        cf.CFBooleanGetValue.argtypes=[p];cf.CFBooleanGetValue.restype=ctypes.c_ubyte
        cf.CFNumberGetValue.argtypes=[p,ctypes.c_int,ctypes.c_void_p];cf.CFNumberGetValue.restype=ctypes.c_ubyte
        cf.CFStringCreateWithCString.argtypes=[p,ctypes.c_char_p,ctypes.c_uint32];cf.CFStringCreateWithCString.restype=p
        cf.CFRelease.argtypes=[p];cf.CFRelease.restype=None
        array=p()
        if c.CopySymbolicHotKeys(ctypes.byref(array)) or not array:
            raise OSError('Elenco delle scorciatoie di sistema non disponibile.')
        keys=[]
        try:
            # These three SDK names are CFSTR macros, not exported symbols.
            keys=[cf.CFStringCreateWithCString(None,name,0x08000100) for name in
                  (b'kHISymbolicHotKeyEnabled',b'kHISymbolicHotKeyCode',b'kHISymbolicHotKeyModifiers')]
            if not all(keys):raise OSError('Scorciatoie di sistema non leggibili.')
            enabled_key,code_key,mods_key=keys
            result=set()
            for i in range(min(2048,cf.CFArrayGetCount(array))):
                item=cf.CFArrayGetValueAtIndex(array,i)
                enabled=cf.CFDictionaryGetValue(item,enabled_key)
                if not enabled or not cf.CFBooleanGetValue(enabled):continue
                code=cf.CFDictionaryGetValue(item,code_key);mods=cf.CFDictionaryGetValue(item,mods_key)
                key_value=ctypes.c_int64();mods_value=ctypes.c_int64()
                if (code and mods and cf.CFNumberGetValue(code,4,ctypes.byref(key_value))
                        and cf.CFNumberGetValue(mods,4,ctypes.byref(mods_value))):
                    result.add((key_value.value,mods_value.value))
            self._reserved=result;return result
        finally:
            for key in keys:
                if key:cf.CFRelease(key)
            cf.CFRelease(array)

    def register(self,ident,sequence):
        try:
            code=self.keycode(int(QKeySequence(sequence)[0].key()))
            modifiers=native_modifiers(sequence,'darwin')
            try:reserved=self.system_shortcuts()
            except (OSError,AttributeError,ValueError) as exc:
                logging.warning('macOS system shortcuts: %s',exc)
                raise ValueError('Impossibile verificare le scorciatoie di macOS') from exc
            if (code,modifiers) in reserved:raise ValueError('Combinazione usata da macOS')
            ref=ctypes.c_void_p()
            status=self.carbon.RegisterEventHotKey(code,modifiers,
                self.ID(self.SIGNATURE,ident),self.carbon.GetApplicationEventTarget(),self.EXCLUSIVE,ctypes.byref(ref))
            if status: return False
            self.registered[ident]=ref;return True
        except OSError:return False

    def handle(self,next_handler,event,user):
        try:
            value=self.ID()
            if self.carbon.GetEventParameter(event,0x2d2d2d2d,0x686b6964,None,ctypes.sizeof(value),None,ctypes.byref(value)): return -9874
            if value.signature!=self.SIGNATURE or value.id not in self.registered: return -9874
            kind=self.carbon.GetEventKind(event)
            if kind==self.HOTKEY_RELEASED: self.pressed.discard(value.id)
            elif kind==self.HOTKEY_PRESSED and value.id not in self.pressed:
                self.pressed.add(value.id);self.callback(value.id)
            elif kind!=self.HOTKEY_PRESSED:return -9874
            return 0
        except Exception:
            logging.exception('macOS hotkey callback');return -9874

    def unregister_all(self):
        for ref in self.registered.values(): self.carbon.UnregisterEventHotKey(ref)
        self.registered.clear();self.pressed.clear();self._reserved=None

    def close(self):
        self.unregister_all()
        if self.handler_ref: self.carbon.RemoveEventHandler(self.handler_ref);self.handler_ref=None


class LocalBackend:
    def __init__(self,pet,callback): self.pet=pet;self.callback=callback;self.registered={}
    def register(self,ident,sequence):
        shortcut=QShortcut(QKeySequence(sequence),self.pet)
        shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        shortcut.activated.connect(lambda:self.callback(ident));self.registered[ident]=shortcut;return True
    def unregister_all(self):
        for shortcut in self.registered.values(): shortcut.setEnabled(False);shortcut.deleteLater()
        self.registered.clear()
    def close(self): self.unregister_all()


class Hotkeys:
    def __init__(self,pet,backend=None):
        self.pet=pet;self.recording=False;self.closed=False;self.errors={}
        self.actions={IDENTS['panel']:pet.open_panel,IDENTS['reminder']:pet.new_reminder,
                      IDENTS['read']:pet.read_clipboard,IDENTS['stop']:pet.stop_speech,
                      IDENTS['study']:lambda:pet.open_panel(tab=6),
                      IDENTS['stopwatch_toggle']:lambda:pet.toggle_stopwatch(),
                      IDENTS['stopwatch_lap']:lambda:pet.lap_stopwatch(),
                      IDENTS['stopwatch_reset']:lambda:pet.stopwatch.reset(),
                      IDENTS['stopwatch_open']:lambda:pet.open_panel(tab=5,subtab=1),
                      IDENTS['metronome_toggle']:lambda:pet.toggle_metronome(),
                      IDENTS['metronome_open']:lambda:pet.open_panel(tab=5,subtab=0),
                      IDENTS['focus_toggle']:lambda:pet.toggle_focus(),
                      IDENTS['focus_open']:lambda:pet.open_panel(tab=4),
                      IDENTS['note']:lambda:pet.new_note(),IDENTS['capture']:lambda:pet.capture_clipboard(),
                      IDENTS['pet_pause']:lambda:pet.set_paused(not pet.paused),
                      IDENTS['quiet']:lambda:pet.toggle_quiet(),
                      IDENTS['pet_visibility']:lambda:pet.toggle_character_visibility()}
        saved=pet.store.preference('shortcuts_'+sys.platform,{})
        if sys.platform=='darwin' and saved==LEGACY_DEFAULTS:
            saved=dict(DEFAULTS);pet.store.set_preference('shortcuts_'+sys.platform,saved)
        self.bindings={**DEFAULTS,**{k:v for k,v in saved.items() if k in ACTIONS}}
        try:
            self.backend=backend or (WindowsBackend(self.dispatch) if sys.platform=='win32' else
                                    MacBackend(self.dispatch) if sys.platform=='darwin' else LocalBackend(pet,self.dispatch))
            self.errors=self.register(self.bindings)
        except Exception:
            logging.exception('Hotkey initialization');self.backend=None
            self.errors={name:'Servizio non disponibile' for name,value in self.bindings.items() if value}
        self.update_status()

    def dispatch(self,ident):
        if self.closed or self.recording or self.pet.closing: return
        if ident in self.actions:QTimer.singleShot(0,lambda:self.invoke(ident))

    def invoke(self,ident):
        if self.closed or self.recording or self.pet.closing:return
        action=self.actions.get(ident)
        if action:
            action()
            feedback=getattr(self.pet,'shortcut_feedback',None)
            if feedback:feedback(next(name for name,value in IDENTS.items() if value==ident))

    def register(self,bindings):
        errors={}
        for name,sequence in bindings.items():
            try:
                sequence=normalize(sequence)
                if sequence and not self.backend.register(IDENTS[name],sequence): errors[name]='Già in uso o riservata dal sistema'
            except ValueError as exc: errors[name]=str(exc)
        return errors

    def apply(self,bindings):
        normalized={name:normalize(bindings.get(name,'')) for name in ACTIONS}
        values=[s for s in normalized.values() if s]
        if len(values)!=len(set(values)): raise ValueError('Assegna combinazioni diverse alle azioni.')
        if self.backend is None: raise ValueError('Scorciatoie non disponibili. Riavvia Yun Jin.')
        self.backend.unregister_all()
        errors=self.register(normalized)
        if errors:
            self.backend.unregister_all();self.errors=self.register(self.bindings);self.update_status()
            raise ValueError('\n'.join(ACTIONS[key]+': '+value+'.' for key,value in errors.items()))
        self.bindings=normalized;self.errors={}
        self.pet.store.set_preference('shortcuts_'+sys.platform,normalized);self.update_status()

    def probe(self,bindings):
        """Check the live OS registry while the shortcut recorder is open."""
        if not self.recording:return {}
        errors={};normalized={};seen={}
        for name in ACTIONS:
            try:
                sequence=normalize(bindings.get(name,''));normalized[name]=sequence
                if sequence and sequence in seen:
                    errors[name]='Già assegnata a '+ACTIONS[seen[sequence]].lower()
                elif sequence:seen[sequence]=name
            except ValueError as exc:errors[name]=str(exc)
        if self.backend is None:return {name:'Scorciatoie non disponibili' for name in normalized if normalized[name]}
        self.backend.unregister_all()
        try:
            errors.update(self.register({k:v for k,v in normalized.items() if k not in errors}))
        finally:self.backend.unregister_all()
        return errors

    def update_status(self):
        self.pet.hotkey_status=('Non disponibili: '+', '.join(ACTIONS[k] for k in self.errors)) if self.errors else (
            'Scorciatoie globali attive.' if sys.platform in ('win32','darwin') else 'Scorciatoie attive nelle finestre di Yun Jin.')

    def label(self,text,name):
        seq=self.bindings.get(name,'')
        return text+(' · '+QKeySequence(seq).toString(QKeySequence.SequenceFormat.NativeText) if seq and name not in self.errors else '')

    def close(self):
        self.closed=True
        if self.backend: self.backend.close()


class ShortcutDialog(QDialog):
    def __init__(self,pet,parent=None):
        super().__init__(parent);self.pet=pet;self.setWindowTitle('Scorciatoie');self.setStyleSheet(STYLE)
        self.resize(680,490);layout=QVBoxLayout(self);layout.setContentsMargins(20,20,20,18);layout.setSpacing(16)
        self.tabs=QTabWidget();layout.addWidget(self.tabs,1)
        self.edits={};self.clear_buttons={}
        self.validation=QTimer(self);self.validation.setSingleShot(True);self.validation.setInterval(180)
        self.validation.timeout.connect(self.validate_edits)
        for category,names in GROUPS:
            page=QWidget();grid=QGridLayout(page);grid.setContentsMargins(4,16,4,4)
            grid.setHorizontalSpacing(20);grid.setVerticalSpacing(10);grid.setColumnMinimumWidth(0,220);grid.setColumnStretch(1,1)
            for row,name in enumerate(names):
                label=ACTIONS[name];grid.addWidget(plain_label(label.split(' · ')[-1]),row,0)
                edit=QKeySequenceEdit(QKeySequence(pet.hotkeys.bindings[name]));edit.setMaximumSequenceLength(1)
                edit.setClearButtonEnabled(False);edit.setAccessibleName(label);grid.addWidget(edit,row,1)
                edit.findChild(QLineEdit).setPlaceholderText('Nessuna')
                clear=icon_button('close','Disattiva '+label.lower(),edit.clear)
                clear.setEnabled(not edit.keySequence().isEmpty());grid.addWidget(clear,row,2)
                edit.keySequenceChanged.connect(lambda sequence,b=clear:b.setEnabled(not sequence.isEmpty()))
                edit.keySequenceChanged.connect(lambda _sequence:self.validation.start())
                self.clear_buttons[name]=clear
                if name in pet.hotkeys.errors:edit.setToolTip(pet.hotkeys.errors[name])
                self.edits[name]=edit
            grid.setRowStretch(len(names),1);self.tabs.addTab(scroll_page(page),category)
        self.error=plain_label('','alert');self.error.hide();layout.addWidget(self.error)
        if pet.hotkeys.errors:
            self.error.setText('\n'.join(ACTIONS[k]+': '+v+'.' for k,v in pet.hotkeys.errors.items()));self.error.show()
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('Salva')
        self.save_button=buttons.button(QDialogButtonBox.StandardButton.Save)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('Annulla')
        reset=buttons.addButton('Ripristina',QDialogButtonBox.ButtonRole.ResetRole)
        reset.clicked.connect(lambda:[edit.setKeySequence(QKeySequence(DEFAULTS[name])) for name,edit in self.edits.items()])
        buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);layout.addWidget(buttons)

    def showEvent(self,event):
        super().showEvent(event);self.pet.hotkeys.recording=True
        # Unregister while recording, so an existing native binding can be captured.
        if self.pet.hotkeys.backend: self.pet.hotkeys.backend.unregister_all()
        self.validation.start(0)

    def values(self):
        return {name:edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText) for name,edit in self.edits.items()}

    def validate_edits(self):
        if not self.isVisible():return
        errors=self.pet.hotkeys.probe(self.values())
        for name,edit in self.edits.items():
            rule='QKeySequenceEdit QLineEdit {border-color:#e3c293;}' if name in errors else ''
            edit.setStyleSheet(rule);edit.setToolTip(errors.get(name,''))
        self.error.setText('\n'.join(ACTIONS[k]+': '+value+'.' for k,value in errors.items()))
        self.error.setVisible(bool(errors));self.save_button.setEnabled(not errors)

    def done(self,result):
        self.validation.stop()
        self.pet.hotkeys.recording=False
        if result!=QDialog.DialogCode.Accepted and self.pet.hotkeys.backend and not self.pet.hotkeys.closed:
            self.pet.hotkeys.backend.unregister_all()
            self.pet.hotkeys.errors=self.pet.hotkeys.register(self.pet.hotkeys.bindings)
            self.pet.hotkeys.update_status()
        super().done(result)

    def save(self):
        self.validation.stop()
        try:
            self.pet.hotkeys.apply(self.values())
        except ValueError as exc:
            self.error.setText(str(exc));self.error.show()
            # Keep recording possible after a rejected combination.
            if self.pet.hotkeys.backend: self.pet.hotkeys.backend.unregister_all()
            return
        self.accept()
