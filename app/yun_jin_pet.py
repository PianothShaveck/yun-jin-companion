#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Windows launcher: keep the companion modules and assets in this folder."""
import sys
import os
try:
    import certifi
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
except ImportError:
    pass
try:
    from yun_jin_windows import set_process_identity
    set_process_identity()
    from yun_jin_app import main
except Exception as exc:
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,
            'Avvio non riuscito: '+str(exc)+'\n\nRiapri Windows.cmd dal pacchetto per installare o riparare le dipendenze.',
            'Yun Jin', 0x10)
        sys.exit(1)
    else:
        raise
else:
    sys.exit(main())
