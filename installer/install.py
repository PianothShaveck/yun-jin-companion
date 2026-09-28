#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Install only in the current user's folders; never change system packages."""
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import shlex
import shutil
import subprocess
import sys
import tempfile
import venv

SOURCE = Path(__file__).resolve().parent.parent
NAME = 'Yun Jin Companion'


def location():
    if sys.platform == 'win32':
        return Path(os.environ.get('LOCALAPPDATA', str(Path.home()/'AppData/Local')))/'YunJinPet'
    if sys.platform == 'darwin':
        return Path.home()/'Library/Application Support/YunJinPet'
    return Path(os.environ.get('XDG_DATA_HOME', str(Path.home()/'.local/share')))/'YunJinPet'


def run(args, **kwargs):
    print('  '+str(args[0])+(' …' if len(args)>1 else ''), flush=True)
    subprocess.run([str(x) for x in args], check=True, **kwargs)


def environment(root):
    env = root/'runtime'/('python-%s.%s' % sys.version_info[:2])
    executable = env/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
    requirements = SOURCE/'installer/requirements.txt'
    signature = hashlib.sha256(requirements.read_bytes()+str(sys.version_info[:2]).encode()+platform.machine().encode()).hexdigest()
    marker = env/'installed.json'
    if not executable.exists():
        print('Creo l’ambiente privato di Yun Jin…', flush=True)
        if env.exists(): shutil.rmtree(env)
        venv.EnvBuilder(with_pip=True, clear=False).create(env)
    ready = False
    try:
        ready = json.loads(marker.read_text())['requirements']==signature
    except (OSError,ValueError,KeyError):
        pass
    if ready:
        ready = subprocess.run([str(executable),'-c','import PyQt6.QtMultimedia, edge_tts, gtts'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
    if not ready:
        print('Installo le dipendenze. Al primo avvio serve Internet…', flush=True)
        run([executable,'-m','pip','install','--disable-pip-version-check','--only-binary=:all:','-r',requirements])
        marker.write_text(json.dumps({'requirements':signature}),encoding='utf-8')
    return executable


def check_running(root):
    """Refuse to replace files of a running instance; use Qt's native lock."""
    # This helper runs in the newly installed environment, where Qt is present.
    code = ('import sys;from PyQt6.QtCore import QLockFile;'
            'lock=QLockFile(sys.argv[1]);lock.setStaleLockTime(0);'
            'ok=lock.tryLock(100);lock.unlock() if ok else None;sys.exit(0 if ok else 2)')
    return code, str(root/'companion.lock')


def deploy(root):
    destination = root/'program'
    staging = Path(tempfile.mkdtemp(prefix='program-new-',dir=root))
    try:
        shutil.copytree(SOURCE/'app',staging/'app',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        shutil.copy2(SOURCE/'Guida.pdf',staging/'Guida.pdf')
        # Keep old program until copying is complete; never touch personal data.
        previous = root/'program-previous'
        if previous.exists(): shutil.rmtree(previous)
        if destination.exists(): destination.rename(previous)
        try:
            staging.rename(destination)
        except Exception:
            if previous.exists() and not destination.exists(): previous.rename(destination)
            raise
        if previous.exists(): shutil.rmtree(previous)
    finally:
        if staging.exists(): shutil.rmtree(staging)
    return destination


def windows_shortcut(executable,program):
    powershell=shutil.which('powershell.exe') or 'powershell.exe'
    script=SOURCE/'installer/shortcut.ps1'
    run([powershell,'-NoProfile','-ExecutionPolicy','Bypass','-File',script,
         '-Python',executable.with_name('pythonw.exe'),'-Program',program])
    run([executable,program/'app/yun_jin_windows.py'])


def mac_shortcut(executable,program,root):
    bundle=Path.home()/'Applications'/f'{NAME}.app'
    contents=bundle/'Contents';binary=contents/'MacOS';resources=contents/'Resources'
    binary.mkdir(parents=True,exist_ok=True);resources.mkdir(exist_ok=True)
    shutil.copy2(program/'app/favicon.icns',resources/'YunJin.icns')
    info={'CFBundleName':NAME,'CFBundleDisplayName':NAME,'CFBundleIdentifier':'pianoth.yunjin.desktoppet.v1',
          'CFBundleVersion':'1.0.0','CFBundleShortVersionString':'1.0','CFBundleExecutable':'YunJin',
          'CFBundlePackageType':'APPL','CFBundleIconFile':'YunJin.icns','LSMinimumSystemVersion':'13.0',
          'NSHighResolutionCapable':True}
    (contents/'Info.plist').write_bytes(plistlib.dumps(info))
    launcher=binary/'YunJin'
    launcher.write_text('#!/bin/sh\nexec '+shlex.quote(str(executable))+' '+shlex.quote(str(program/'app/yun_jin_pet.py'))+
                        ' >> '+shlex.quote(str(root/'launcher.log'))+' 2>&1\n',encoding='utf-8')
    launcher.chmod(0o755)
    desktop=Path.home()/'Desktop'/f'{NAME}.app'
    if not desktop.exists() and not desktop.is_symlink():
        try:desktop.symlink_to(bundle)
        except OSError: print('Trascina l’app da ~/Applications alla Scrivania per creare un alias.')
    return bundle


def linux_shortcut(executable,program,root):
    # Desktop Entry Exec has its own escaping rules, different from shell quoting.
    def quote(value):
        return '"'+str(value).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')+'"'
    entries=Path.home()/'.local/share/applications';entries.mkdir(parents=True,exist_ok=True)
    file=entries/'yun-jin-companion.desktop'
    file.write_text('[Desktop Entry]\nType=Application\nName='+NAME+'\nComment=Appunti, tempo e musica\nExec='+
        quote(executable)+' '+quote(program/'app/yun_jin_pet.py')+'\nIcon='+str(program/'app/favicon.png')+
        '\nTerminal=false\nCategories=Utility;\n',encoding='utf-8');file.chmod(0o755)
    desktop=Path.home()/'Desktop'
    if shutil.which('xdg-user-dir'):
        candidate=subprocess.run(['xdg-user-dir','DESKTOP'],capture_output=True,text=True)
        if candidate.returncode==0 and candidate.stdout.strip(): desktop=Path(candidate.stdout.strip())
    if desktop.is_dir() and desktop!=Path.home():
        target=desktop/file.name
        if not target.exists():shutil.copy2(file,target)


def main():
    if not (3,10)<=sys.version_info[:2]<(3,15):
        raise RuntimeError('Serve Python 3.10–3.14 a 64 bit. Usa il programma di avvio incluso.')
    if sys.maxsize<=2**32:raise RuntimeError('Serve Python a 64 bit.')
    if sys.platform=='darwin' and int(platform.mac_ver()[0].split('.')[0])<13:
        raise RuntimeError('Questa versione richiede macOS 13 o successivo.')
    root=location();root.mkdir(parents=True,exist_ok=True)
    executable=environment(root)
    code,lock=check_running(root)
    result=subprocess.run([str(executable),'-c',code,lock])
    if result.returncode==2:
        print('Yun Jin è già aperta. Chiudila dal suo menu e riapri questo programma per aggiornare.',flush=True)
        return 2
    if result.returncode:raise RuntimeError('Non riesco a controllare l’istanza già aperta.')
    program=deploy(root)
    if sys.platform=='win32':
        windows_shortcut(executable,program)
        subprocess.Popen([str(executable.with_name('pythonw.exe')),str(program/'app/yun_jin_pet.py')],cwd=program)
    elif sys.platform=='darwin':
        bundle=mac_shortcut(executable,program,root);run(['open',bundle])
    else:
        linux_shortcut(executable,program,root)
        with open(root/'launcher.log','ab') as log:
            subprocess.Popen([str(executable),str(program/'app/yun_jin_pet.py')],stdout=log,stderr=log,start_new_session=True)
    print('Installazione completata. D’ora in poi usa Yun Jin Companion sul desktop.',flush=True)
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print('\nInstallazione non riuscita: '+str(exc)+'\nConsulta Guida.pdf; i dati personali sono conservati.',file=sys.stderr)
        sys.exit(1)
