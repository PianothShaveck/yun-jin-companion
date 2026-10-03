# SPDX-License-Identifier: GPL-3.0-or-later
"""A retained native menu-bar item, independent of the avatar and the Dock."""
import ctypes as C
import logging
import platform
import time
import weakref
from pathlib import Path
from PyQt6 import sip
from PyQt6.QtCore import QObject,QTimer
from PyQt6.QtGui import QIcon
from yun_jin_macos import AppKit

_targets=weakref.WeakValueDictionary()
_callbacks=[]

class Size(C.Structure):
    _fields_=[('width',C.c_double),('height',C.c_double)]
class Point(C.Structure):
    _fields_=[('x',C.c_double),('y',C.c_double)]
class Rect(C.Structure):
    _fields_=[('origin',Point),('size',Size)]

def status_icon():
    icon=QIcon(str(Path(__file__).parent/'favicon.png'))
    icon.setIsMask(False)
    return icon

class NativeStatusItem(AppKit):
    def __init__(self,on_open,on_action,on_close):
        super().__init__()
        self.on_open=on_open;self.on_action=on_action;self.on_close=on_close
        self.item=None;self.menu=None;self.target=None;self.image=None
        self.bar=self.send(self.cls('NSStatusBar'),'systemStatusBar')
        try:
            self.set_accessory(True)
            self.target=self.send(self.send(self.target_class(),'alloc'),'init')
            _targets[self.target]=self
            self.menu=self.send(self.send(self.cls('NSMenu'),'alloc'),'initWithTitle:',types=(C.c_void_p,),args=(self.string('Yun Jin'),))
            self.send(self.menu,'setAutoenablesItems:',None,(C.c_bool,),(False,))
            self.send(self.menu,'setDelegate:',None,(C.c_void_p,),(self.target,))
            self.image=self.send(self.send(self.cls('NSImage'),'alloc'),'initWithContentsOfFile:',
                                 types=(C.c_void_p,),args=(self.string(str(Path(__file__).parent/'favicon.png')),))
            if not self.image:raise RuntimeError('Icona di Yun Jin non disponibile.')
            self.send(self.image,'setSize:',None,(Size,),(Size(18,18),))
            self.send(self.image,'setTemplate:',None,(C.c_bool,),(False,))
            self.create_item()
        except Exception:
            self.close();raise

    def string(self,text):
        return self.send(self.cls('NSString'),'stringWithUTF8String:',types=(C.c_char_p,),args=(text.encode('utf-8'),))

    def target_class(self):
        name=b'YunJinStatusTarget'
        found=self.objc.objc_getClass(name)
        if found:return found
        self.objc.objc_allocateClassPair.argtypes=[C.c_void_p,C.c_char_p,C.c_size_t]
        self.objc.objc_allocateClassPair.restype=C.c_void_p
        self.objc.class_addMethod.argtypes=[C.c_void_p,C.c_void_p,C.c_void_p,C.c_char_p]
        self.objc.class_addMethod.restype=C.c_bool
        self.objc.objc_registerClassPair.argtypes=[C.c_void_p]
        self.objc.objc_registerClassPair.restype=None
        cls=self.objc.objc_allocateClassPair(self.cls('NSObject'),name,0)
        if not cls:raise RuntimeError('Impossibile creare il menu di Yun Jin.')
        def invoke(receiver,selector,argument):
            native=_targets.get(receiver)
            if native is None:return
            try:
                if selector==native.objc.sel_registerName(b'menuWillOpen:'):native.on_open()
                elif selector==native.objc.sel_registerName(b'menuDidClose:'):native.on_close()
                else:native.on_action(native.send(argument,'tag',C.c_long))
            except Exception:logging.exception('Yun Jin menu-bar action')
        callback=C.CFUNCTYPE(None,C.c_void_p,C.c_void_p,C.c_void_p)(invoke)
        _callbacks.append(callback)  # Keep the Python IMP alive until process exit.
        for selector in (b'menuWillOpen:',b'menuDidClose:',b'yunJinAction:'):
            if not self.objc.class_addMethod(cls,self.objc.sel_registerName(selector),C.cast(callback,C.c_void_p),b'v@:@'):
                raise RuntimeError('Impossibile collegare il menu di Yun Jin.')
        def notification_clicked(receiver,selector,center,notification):
            native=_targets.get(receiver)
            if native:
                try:native.on_action(-1)
                except Exception:logging.exception('Yun Jin notification action')
        click=C.CFUNCTYPE(None,C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p)(notification_clicked)
        _callbacks.append(click)
        self.objc.class_addMethod(cls,self.objc.sel_registerName(b'userNotificationCenter:didActivateNotification:'),C.cast(click,C.c_void_p),b'v@:@@')
        self.objc.objc_registerClassPair(cls)
        return cls

    def rect(self,receiver,selector):
        if platform.machine().lower() in ('x86_64','amd64'):
            # Intel returns a 32-byte NSRect through objc_msgSend_stret.
            value=Rect()
            fn=C.CFUNCTYPE(None,C.POINTER(Rect),C.c_void_p,C.c_void_p)(C.cast(self.objc.objc_msgSend_stret,C.c_void_p).value)
            fn(C.byref(value),receiver,self.objc.sel_registerName(selector.encode()))
            return value
        return self.send(receiver,selector,Rect)

    def create_item(self):
        self.remove_item()
        # Keep a fixed hit area around the favicon; AppKit owns placement.
        self.item=self.send(self.bar,'statusItemWithLength:',types=(C.c_double,),args=(32.0,))
        if not self.item:raise RuntimeError('Barra menu macOS non disponibile.')
        self.send(self.item,'retain')
        button=self.send(self.item,'button')
        self.send(button,'setImage:',None,(C.c_void_p,),(self.image,))
        self.send(button,'setToolTip:',None,(C.c_void_p,),(self.string('Yun Jin Companion'),))
        self.send(button,'setAccessibilityLabel:',None,(C.c_void_p,),(self.string('Yun Jin Companion'),))
        self.send(self.item,'setMenu:',None,(C.c_void_p,),(self.menu,))
        self.show()

    def show(self):
        if self.item:self.send(self.item,'setVisible:',None,(C.c_bool,),(True,))

    def is_available(self):
        if not self.item or not self.send(self.item,'isVisible',C.c_bool):return False
        button=self.send(self.item,'button');window=self.send(button,'window')
        if not window:return False
        frame=self.rect(window,'frame')
        if frame.size.width<=0 or frame.size.height<=0:return False
        screen=self.send(window,'screen')
        if screen:
            # A nonempty frame alone is insufficient on a notched MacBook.
            safe=self.rect(screen,'auxiliaryTopRightArea')
            if safe.size.width>0 and frame.origin.x<safe.origin.x:return False
        return True

    def set_menu(self,entries):
        self.send(self.menu,'removeAllItems',None)
        def add(menu,entries):
            for entry in entries:
                if entry is None:
                    item=self.send(self.cls('NSMenuItem'),'separatorItem')
                    self.send(menu,'addItem:',None,(C.c_void_p,),(item,));continue
                tag,title,enabled,checked,children=entry
                item=self.send(self.send(self.cls('NSMenuItem'),'alloc'),'initWithTitle:action:keyEquivalent:',
                    types=(C.c_void_p,C.c_void_p,C.c_void_p),
                    args=(self.string(title),self.objc.sel_registerName(b'yunJinAction:'),self.string('')))
                try:
                    self.send(item,'setTarget:',None,(C.c_void_p,),(self.target,))
                    self.send(item,'setTag:',None,(C.c_long,),(tag,))
                    self.send(item,'setEnabled:',None,(C.c_bool,),(enabled,))
                    self.send(item,'setState:',None,(C.c_long,),(int(checked),))
                    if children is not None:
                        submenu=self.send(self.send(self.cls('NSMenu'),'alloc'),'initWithTitle:',types=(C.c_void_p,),args=(self.string(title),))
                        try:
                            self.send(submenu,'setAutoenablesItems:',None,(C.c_bool,),(False,))
                            add(submenu,children)
                            self.send(item,'setSubmenu:',None,(C.c_void_p,),(submenu,))
                        finally:self.send(submenu,'release',None)
                    self.send(menu,'addItem:',None,(C.c_void_p,),(item,))
                finally:self.send(item,'release',None)
        add(self.menu,entries)

    def remove_item(self):
        if self.item:
            self.send(self.bar,'removeStatusItem:',None,(C.c_void_p,),(self.item,))
            self.send(self.item,'release',None);self.item=None

    def show_message(self,title,message):
        # Preserve the notification path used by Qt's Cocoa tray backend.
        cls=self.cls('NSUserNotification');center_cls=self.cls('NSUserNotificationCenter')
        if not cls or not center_cls:return
        center=self.send(center_cls,'defaultUserNotificationCenter')
        notification=self.send(self.send(cls,'alloc'),'init')
        try:
            self.send(notification,'setTitle:',None,(C.c_void_p,),(self.string(title),))
            self.send(notification,'setInformativeText:',None,(C.c_void_p,),(self.string(message),))
            self.send(center,'setDelegate:',None,(C.c_void_p,),(self.target,))
            self.send(center,'deliverNotification:',None,(C.c_void_p,),(notification,))
            self.send(center,'performSelector:withObject:afterDelay:',None,(C.c_void_p,C.c_void_p,C.c_double),
                      (self.objc.sel_registerName(b'removeDeliveredNotification:'),notification,10.0))
        finally:self.send(notification,'release',None)

    def close(self):
        self.remove_item()
        center=self.send(self.cls('NSUserNotificationCenter'),'defaultUserNotificationCenter')
        if center and self.target and self.send(center,'delegate')==self.target:
            self.send(center,'setDelegate:',None,(C.c_void_p,),(None,))
        if self.menu:
            self.send(self.menu,'setDelegate:',None,(C.c_void_p,),(None,))
            self.send(self.menu,'removeAllItems',None)
        _targets.pop(self.target,None)
        for attr in ('menu','target','image'):
            obj=getattr(self,attr,None)
            if obj:self.send(obj,'release',None);setattr(self,attr,None)

class MacAccess(QObject):
    def __init__(self,app,pet,native_factory=NativeStatusItem):
        super().__init__(app)
        self.app=app;self.pet=pet;self.closed=False;self.actions={};self.pending=None;self.opened=None
        self.repair_attempted=False
        self.refresh_timer=QTimer(self);self.refresh_timer.setSingleShot(True)
        self.refresh_timer.timeout.connect(self.refresh)
        self.retry_timer=QTimer(self);self.retry_timer.setSingleShot(True);self.retry_timer.setInterval(2000)
        self.retry_timer.timeout.connect(self.verify_repair)
        self.action_timer=QTimer(self);self.action_timer.setSingleShot(True)
        self.action_timer.timeout.connect(self.run_action)
        self.native=native_factory(self.menu_opened,self.queue_action,self.menu_closed)
        try:self.prepare_menu()
        except Exception:
            self.native.close();raise
        pet.tray.hide()  # One status item; the native item owns the Mac menu.
        self.app.screenAdded.connect(self.visibility_changed)
        self.app.screenRemoved.connect(self.visibility_changed)
        self.app.aboutToQuit.connect(self.close);pet.destroyed.connect(self.close)
        self.visibility_changed()

    def menu_opened(self):
        if self.closed:return
        if self.opened is None:
            self.opened=time.monotonic();self.previous_menu_open=self.pet.menu_open;self.pet.menu_open=True
        self.prepare_menu()

    def menu_closed(self):
        if self.opened is not None:
            self.pet.follow_until+=time.monotonic()-self.opened
            self.pet.last_tick=time.monotonic();self.pet.menu_open=self.previous_menu_open;self.opened=None

    def prepare_menu(self):
        if self.closed or self.pet.closing:return
        menu=self.pet.tray_menu
        self.pet.populate_context_menu(menu)
        visibility=next(a for a in menu.actions() if a.objectName()=='character_visibility')
        menu.removeAction(visibility);menu.insertAction(menu.actions()[0],visibility)
        self.actions={}
        def entries(menu):
            result=[]
            for action in menu.actions():
                if not action.isVisible():continue
                if action.isSeparator():result.append(None);continue
                tag=len(self.actions)+1;self.actions[tag]=action
                result.append((tag,action.text(),action.isEnabled(),action.isChecked(),
                               entries(action.menu()) if action.menu() else None))
            return result
        self.native.set_menu(entries(menu))

    def queue_action(self,tag):
        if self.closed:return
        self.pending=(lambda:self.pet.open_panel(tab=1)) if tag==-1 else self.actions.get(tag)
        self.action_timer.start(0)  # Let the native menu finish tracking first.

    def run_action(self):
        action=self.pending;self.pending=None
        if self.closed or self.pet.closing or action is None:return
        if callable(action):action()
        elif not sip.isdeleted(action) and action.isEnabled():action.trigger()

    def is_available(self):
        return not self.closed and self.native.is_available()

    def visibility_changed(self,*_):
        if not self.closed and not self.refresh_timer.isActive():self.refresh_timer.start(0)

    def refresh(self):
        if self.closed or self.pet.closing:return
        try:
            self.native.set_accessory(True);self.native.show()
            if self.native.is_available():
                self.retry_timer.stop();self.repair_attempted=False
            elif not self.retry_timer.isActive():
                # At launch AppKit reports a zero-height window even for a
                # working item. Allow its first layout before recreating it.
                self.repair_attempted=False
                self.retry_timer.start()
        except Exception:
            logging.exception('Unable to restore Yun Jin menu-bar item')

    def verify_repair(self):
        if self.closed or self.pet.closing:return
        try:
            if self.native.is_available():self.repair_attempted=False
            elif not self.repair_attempted:
                self.repair_attempted=True;self.native.create_item();self.retry_timer.start()
            else:
                logging.warning('Yun Jin menu-bar item is not visible after repair')
        except Exception:
            logging.exception('Unable to restore Yun Jin menu-bar item')

    def close(self,*_):
        if self.closed:return
        self.closed=True
        self.menu_closed()
        for timer in (self.refresh_timer,self.retry_timer,self.action_timer):timer.stop()
        self.pending=None;self.actions.clear();self.native.close()
