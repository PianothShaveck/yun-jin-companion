import importlib.util,tempfile,subprocess,plistlib,os
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('installer',Path(__file__).resolve().parents[1]/'installer/install.py')
i=importlib.util.module_from_spec(spec);spec.loader.exec_module(i)
with tempfile.TemporaryDirectory(prefix='yun jin test ') as tmp:
 root=Path(tmp)/'data';root.mkdir();(root/'companion.sqlite3').write_bytes(b'personal-data-sentinel')
 (root/'attachments').mkdir();(root/'attachments/test.png').write_bytes(b'capture')
 (root/'program').mkdir();(root/'program/obsolete.py').write_text('old')
 program=i.deploy(root)
 assert (root/'companion.sqlite3').read_bytes()==b'personal-data-sentinel'
 assert (root/'attachments/test.png').read_bytes()==b'capture'
 assert not (program/'obsolete.py').exists()
 assert (program/'app/yun_jin_music.py').exists() and (program/'Guida.pdf').exists()
 home=Path(tmp)/'home';home.mkdir();(home/'Desktop').mkdir()
 exe=home/'runtime/bin/python'
 with patch.object(Path,'home',return_value=home):
  bundle=i.mac_shortcut(exe,program,root)
  info=plistlib.loads((bundle/'Contents/Info.plist').read_bytes())
  assert info['CFBundleIdentifier']=='pianoth.yunjin.desktoppet.v1'
  # Resolve both paths: macOS temporary directories can pass through /var -> /private/var.
  assert (home/'Desktop/Yun Jin Companion.app').resolve()==bundle.resolve()
  launcher=bundle/'Contents/MacOS/YunJin';assert launcher.stat().st_mode&0o111
  subprocess.run(['sh','-n',str(launcher)],check=True)
 print('PASS installer: deployment preserves personal files, removes old program files, installs guide, creates valid Mac app bundle and executable desktop alias.')
