"""Exercise real ZIP validation and file transactions in disposable directories."""
import hashlib, io, json, os, shutil, stat, subprocess, sys, tempfile, time, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import yun_jin_update as u

REQUIRED=['app/yun_jin_pet.py','app/yun_jin_app.py','app/yun_jin_platform.py',
          'app/assets/animations.json','app/spritesheet-yun-jin-v2.png','Guida.pdf',
          'installer/install.py','Mac.command']

def fixture(root,version='1.2.0',entry=None,extra=None):
 root=Path(root);root.mkdir(parents=True,exist_ok=True)
 files={name:('new '+name).encode() for name in REQUIRED}
 if entry is not None:files['app/yun_jin_pet.py']=entry.encode()
 if extra:files.update(extra)
 for name,data in files.items():
  p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
 doc=dict(protocol=1,version=version,requirements={'PyQt6':'6.11.0'},
          files={name:hashlib.sha256(data).hexdigest() for name,data in files.items()})
 (root/'app'/u.MANIFEST).write_text(json.dumps(doc),encoding='utf-8')
 return root

def archive(root):
 buffer=io.BytesIO()
 with zipfile.ZipFile(buffer,'w') as z:
  for p in Path(root).rglob('*'):
   if p.is_file():z.write(p,'Yun-Jin-Companion-1.2.0/'+p.relative_to(root).as_posix())
 return buffer.getvalue()

def release():
 return dict(tag_name='v1.2.0',draft=False,prerelease=False,body='## Novità\nCorrezione',
   html_url=u.RELEASES_URL+'/tag/v1.2.0',assets=[dict(name='Yun-Jin-Companion-1.2.0.zip',state='uploaded',
   browser_download_url=u.RELEASES_URL+'/download/v1.2.0/Yun-Jin-Companion-1.2.0.zip',size=1200,
   digest='sha256:'+'a'*64)])

class UpdateTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def test_stable_semantic_versions_and_exact_runtime_asset(self):
  data=release();data['assets'].insert(0,dict(data['assets'][0],name='Yun-Jin-Companion-1.2.0-Sorgenti.zip'))
  result=u.release_from_json(data,'1.1.0');self.assertTrue(result['automatic'])
  self.assertEqual(result['notes'],data['body']);self.assertIn('/Yun-Jin-Companion-1.2.0.zip',result['download'])
  self.assertIsNone(u.release_from_json(data,'1.10.0'))
  data['prerelease']=True;self.assertIsNone(u.release_from_json(data,'1.1.0'))
 def test_missing_asset_or_digest_never_installs(self):
  data=release();data['assets'][0]['digest']=None
  self.assertFalse(u.release_from_json(data,'1.1.0')['automatic'])
  data['assets']=[];self.assertFalse(u.release_from_json(data,'1.1.0')['automatic'])
 def test_foreign_insecure_urls_rejected(self):
  for url in ['http://github.com/'+u.REPOSITORY+'/releases/tag/v1.2.0',
    'https://evil.example/a','https://github.com.evil.test/'+u.REPOSITORY+'/releases/a',
    'https://github.com/another/repository/releases/a','https://evil@github.com/'+u.REPOSITORY+'/releases/a']:
   data=release();data['assets'][0]['browser_download_url']=url
   with self.assertRaises(ValueError):u.release_from_json(data,'1.1.0')
 def test_path_traversal_duplicates_links_and_bombs_rejected(self):
  # ZipInfo replaces backslashes with forward slashes on Windows. Check the
  # raw separator at the validator, and use ZIP paths that remain unsafe
  # after that normalization so this fixture has the same meaning on all OSes.
  with self.assertRaisesRegex(ValueError,'Percorso non sicuro'):
   u.safe_relative('release/evil\\escape')
  for name,mode in [('../escape',0),('release/../../escape',0),('release/evil\\../escape',0),('/absolute',0),
                    ('release/shortcut',stat.S_IFLNK|0o777)]:
   with self.subTest(name=name,mode=mode):
    raw=io.BytesIO()
    with zipfile.ZipFile(raw,'w') as z:
     info=zipfile.ZipInfo(name);info.external_attr=mode<<16;z.writestr(info,'target')
    with self.assertRaises(ValueError):u.unpack_verified(io.BytesIO(raw.getvalue()),self.root/'out','1.2.0')
    self.assertFalse((self.root/'out').exists())
  raw=io.BytesIO()
  with zipfile.ZipFile(raw,'w') as z:
   z.writestr('release/a','a');z.writestr('release/A','b')
  with self.assertRaises(ValueError):u.unpack_verified(io.BytesIO(raw.getvalue()),self.root/'out','1.2.0')
 def test_valid_zip_and_manifest_tampering(self):
  source=fixture(self.root/'source')
  out=u.unpack_verified(io.BytesIO(archive(source)),self.root/'out','1.2.0')
  self.assertEqual(u.verify_program(out)['version'],'1.2.0')
  (out/'app/yun_jin_pet.py').write_text('tampered')
  with self.assertRaisesRegex(ValueError,'danneggiato'):u.verify_program(out)
 def test_bad_download_never_reaches_destination(self):
  data=u.release_from_json(release(),'1.1.0');data.update(size=3,digest='a'*64)
  with patch.object(u,'open_url',return_value=io.BytesIO(b'bad')):
   with self.assertRaisesRegex(ValueError,'SHA-256'):u.prepare_update(data,self.root/'cache')
  self.assertEqual(list((self.root/'cache').iterdir()),[])
 def test_download_verify_and_prepare(self):
  raw=archive(fixture(self.root/'source'));data=u.release_from_json(release(),'1.1.0')
  data.update(size=len(raw),digest=hashlib.sha256(raw).hexdigest())
  progress=[]
  with patch.object(u,'open_url',return_value=io.BytesIO(raw)),patch.object(u,'check_compatibility'):
   path=u.prepare_update(data,self.root/'cache',progress.append)
  self.assertEqual(u.verify_program(path)['version'],'1.2.0');self.assertEqual(progress[-1],100)
 def test_moved_install_preserves_user_data_and_unknown_files(self):
  source=fixture(self.root/'source')
  moved=self.root/'Documents'/'Yun Jin con spazi è';moved.mkdir(parents=True)
  app=moved/'app';app.mkdir();(app/'yun_jin_pet.py').write_text('old')
  (app/'personal.txt').write_text('keep');(moved/'notes.sqlite3').write_bytes(b'my notes')
  elsewhere=self.root/'default-app';elsewhere.mkdir();(elsewhere/'sentinel').write_text('untouched')
  u.transaction(source,app,self.root/'backup',self.root/'journal.json')
  self.assertEqual((app/'yun_jin_pet.py').read_text(),'new app/yun_jin_pet.py')
  self.assertEqual((app/'personal.txt').read_text(),'keep');self.assertEqual((moved/'notes.sqlite3').read_bytes(),b'my notes')
  self.assertEqual((elsewhere/'sentinel').read_text(),'untouched')
  self.assertFalse((moved/'installer').exists())
 def test_flat_python_folder_updates_in_place(self):
  source=fixture(self.root/'source')
  flat=self.root/'Yun Jin';flat.mkdir()
  for p in (source/'app').rglob('*'):
   if p.is_file():
    dest=flat/p.relative_to(source/'app');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
  (flat/'yun_jin_pet.py').write_text('old')
  u.transaction(source,flat,self.root/'backup',self.root/'journal.json')
  self.assertEqual((flat/'yun_jin_pet.py').read_text(),'new app/yun_jin_pet.py')
 def test_portable_launchers_updated_obsolete_managed_removed(self):
  source=fixture(self.root/'source')
  old=fixture(self.root/'portable','1.1.0',extra={'app/obsolete.py':b'old'})
  (old/'Mac.command').write_text('old launcher')
  u.transaction(source,old/'app',self.root/'backup',self.root/'journal.json')
  self.assertFalse((old/'app/obsolete.py').exists());self.assertEqual((old/'Mac.command').read_text(),'new Mac.command')
 def test_failure_halfway_rolls_back_every_file(self):
  source=fixture(self.root/'source');old=fixture(self.root/'old','1.1.0',entry='original launcher')
  before={p.relative_to(old):p.read_bytes() for p in old.rglob('*') if p.is_file()}
  real=u.atomic_copy;count=0
  def fail_once(src,dest):
   nonlocal count
   count+=1
   if count==4:raise OSError('disk failure')
   return real(src,dest)
  with patch.object(u,'atomic_copy',side_effect=fail_once):
   with self.assertRaisesRegex(OSError,'disk failure'):u.transaction(source,old/'app',self.root/'backup',self.root/'journal.json')
  after={p.relative_to(old):p.read_bytes() for p in old.rglob('*') if p.is_file()}
  self.assertEqual(before,after)
  self.assertEqual(json.loads((self.root/'journal.json').read_text())['status'],'rolled_back')
 def test_symlink_destination_never_changes_outside_file(self):
  source=fixture(self.root/'source');target=self.root/'target';target.mkdir()
  outside=self.root/'outside';outside.write_text('safe')
  try:(target/'yun_jin_pet.py').symlink_to(outside)
  except OSError:self.skipTest('Symlinks unavailable')
  with self.assertRaises(ValueError):u.transaction(source,target,self.root/'backup',self.root/'journal.json')
  self.assertEqual(outside.read_text(),'safe')
 def test_restart_worker_and_failed_start_rollback(self):
  # Real detached process + real Qt file lock, with a tiny stand-in for the GUI.
  from PyQt6.QtCore import QLockFile
  for succeeds in (True,False):
   work=self.root/str(succeeds);work.mkdir()
   old_entry="import os\nfrom pathlib import Path\nPath(os.environ['YUN_JIN_UPDATE_RESULT']).with_name('old-restarted').touch()\n"
   old=fixture(work/'running','1.1.0',entry=old_entry)
   ready_entry="import os\nfrom pathlib import Path\nPath(os.environ['YUN_JIN_UPDATE_READY']).write_text(os.environ['YUN_JIN_UPDATE_TOKEN'])\n"
   source=fixture(work/'source',entry=ready_entry if succeeds else 'raise RuntimeError("broken release")')
   lock=QLockFile(str(work/'app.lock'));lock.setStaleLockTime(0);self.assertTrue(lock.tryLock(100))
   plan=dict(source=str(source),app_dir=str(old/'app'),executable=sys.executable,version='1.2.0',lock=str(work/'app.lock'),token='test-token')
   (work/'plan.json').write_text(json.dumps(plan))
   process=subprocess.Popen([sys.executable,str(ROOT/'app/yun_jin_update.py'),'--worker',str(work/'plan.json')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
   try:
    deadline=time.monotonic()+10
    while not (work/'worker-ready.json').exists() and time.monotonic()<deadline:time.sleep(.05)
    self.assertTrue((work/'worker-ready.json').is_file());self.assertEqual((old/'app/yun_jin_pet.py').read_text(),old_entry)
    lock.unlock();out,err=process.communicate(timeout=20)
    self.assertEqual(process.returncode,0 if succeeds else 1,(out,err))
    result=json.loads((work/'result.json').read_text());self.assertEqual(result['ok'],succeeds)
    if not succeeds:
     self.assertEqual((old/'app/yun_jin_pet.py').read_text(),old_entry)
     deadline=time.monotonic()+5
     while not (work/'old-restarted').exists() and time.monotonic()<deadline:time.sleep(.05)
     self.assertTrue((work/'old-restarted').is_file())
     time.sleep(.15)  # Let the tiny restarted process release its Windows cwd/log handles.
   finally:
    lock.unlock()
    if process.poll() is None:process.kill();process.wait()

 def test_power_loss_recovery_before_gui_import(self):
  source=fixture(self.root/'source');old=fixture(self.root/'old','1.1.0',entry='original')
  data=self.root/'data';work=data/'updates/update-interrupted';work.mkdir(parents=True)
  u.transaction(source,old/'app',work/'backup',work/'journal.json')
  journal=json.loads((work/'journal.json').read_text());journal['status']='applying'
  u.write_json(work/'journal.json',journal)
  u.write_json(data/'updates/pending.json',dict(work=str(work),app_dir=str(old/'app')))
  with patch.dict(os.environ,{},clear=False):
   os.environ.pop('YUN_JIN_UPDATE_READY',None)
   self.assertEqual(u.recover_pending(old/'app',data),'restart')
  self.assertEqual((old/'app/yun_jin_pet.py').read_text(),'original')
  self.assertFalse((data/'updates/pending.json').exists())

if __name__=='__main__':unittest.main(verbosity=2)
