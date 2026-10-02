# SPDX-License-Identifier: GPL-3.0-or-later
"""Platform-specific shortcuts and release information."""
import sys
VERSION = '1.3.1'

def shortcut(key):
    return ('Ctrl+Alt+'+key.upper()) if sys.platform=='win32' else ''

def action_label(text,key):
    value=shortcut(key)
    return text+(' · '+value if value else '')

def shortcut_help():
    return 'Doppio clic su Yun Jin: pannello · Clic destro: menu\nPersonalizza i tasti in Impostazioni → Scorciatoie.'


def mac_dock_icon(path):
    """Set the running process's Dock icon on the Qt GUI thread, without PyObjC.

    The .app icon does not propagate reliably when its launcher execs Python.
    Use AppKit's public NSApplication icon property after Qt creates NSApp.
    """
    if sys.platform != 'darwin':
        return False
    import ctypes
    import logging
    from pathlib import Path
    image = None
    try:
        path = Path(path).resolve(strict=True)
        appkit = ctypes.CDLL('/System/Library/Frameworks/AppKit.framework/AppKit')
        objc = ctypes.CDLL('/usr/lib/libobjc.A.dylib')
        ptr = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        objc.objc_getClass.restype = ptr
        objc.sel_registerName.argtypes = [ctypes.c_char_p]
        objc.sel_registerName.restype = ptr
        address = ctypes.cast(objc.objc_msgSend, ptr).value

        def send(receiver, selector, result=ptr, types=(), args=()):
            # Every signature is explicit, including void returns, on Intel/ARM64.
            call = ctypes.CFUNCTYPE(result, ptr, ptr, *types)(address)
            return call(receiver, objc.sel_registerName(selector), *args)

        ns_path = send(objc.objc_getClass(b'NSString'), b'stringWithUTF8String:',
                       types=(ctypes.c_char_p,), args=(str(path).encode('utf-8'),))
        image = send(objc.objc_getClass(b'NSImage'), b'alloc')
        image = send(image, b'initWithContentsOfFile:', types=(ptr,), args=(ns_path,))
        if not image:
            raise RuntimeError('Cannot load Dock icon: '+str(path))
        application = send(objc.objc_getClass(b'NSApplication'), b'sharedApplication')
        send(application, b'setApplicationIconImage:', None, (ptr,), (image,))
        installed = send(application, b'applicationIconImage')
        send(send(application, b'dockTile'), b'display', None)
        return bool(installed)
    except Exception:
        logging.exception('Unable to set Yun Jin macOS Dock icon')
        return False
    finally:
        if image:
            send(image, b'release', None)
