"""Source-update cleanup preserves unrelated files and external symlinks."""
from pathlib import Path
import sys,tempfile,unittest,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from prune_legacy_calendar_assets import prune


class CalendarMigrationTests(unittest.TestCase):
    def test_remove_only_known_obsolete_names_and_keep_user_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            folder=root/'app/assets/calendar-preview';folder.mkdir(parents=True)
            (folder.parent/'calendar-index.json').write_text(json.dumps({'images':{'YJ-001.webp':{'file':'YJ-001.jxl'}}}))
            for name in ('m01-a.webp','m12-f.webp','m01-z.webp','YJ-001.webp','personal.txt'):
                (folder/name).write_bytes(b'preserve unless managed')
            self.assertEqual({p.name for p in prune(root)}, {'m01-a.webp','m12-f.webp'})
            self.assertEqual({p.name for p in folder.iterdir()}, {'m01-z.webp','YJ-001.webp','personal.txt'})
            self.assertEqual(prune(root), [])

    def test_linked_asset_directory_is_not_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);outside=root/'personal';outside.mkdir();(outside/'m01-a.webp').write_bytes(b'personal')
            assets=root/'app/assets';assets.mkdir(parents=True)
            (assets/'calendar-index.json').write_text(json.dumps({'images':{'YJ-001.webp':{'file':'YJ-001.jxl'}}}))
            try:(assets/'calendar').symlink_to(outside,target_is_directory=True)
            except OSError:self.skipTest('Symlinks not available')
            self.assertEqual(prune(root), [])
            self.assertEqual((outside/'m01-a.webp').read_bytes(), b'personal')

    def test_keep_indexed_codec_and_remove_only_obsolete_originals(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);folder=root/'app/assets/calendar';folder.mkdir(parents=True)
            records={'YJ-085.webp':{'file':'YJ-085.jxl'},'YJ-086.webp':{'file':'YJ-086.webp'}}
            (folder.parent/'calendar-index.json').write_text(json.dumps({'images':records}))
            for name in ('YJ-085.webp','YJ-085.jxl','YJ-086.webp','YJ-086.jxl','YJ-999.webp','personal.png'):
                (folder/name).write_bytes(b'asset')
            self.assertEqual({p.name for p in prune(root)}, {'YJ-085.webp','YJ-086.jxl'})
            self.assertEqual({p.name for p in folder.iterdir()}, {'YJ-085.jxl','YJ-086.webp','YJ-999.webp','personal.png'})

    def test_missing_or_old_catalog_does_not_remove_anything(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);folder=root/'app/assets/calendar';folder.mkdir(parents=True)
            path=folder/'m01-a.webp';path.write_bytes(b'old')
            self.assertEqual(prune(root), [])
            (folder.parent/'calendar-index.json').write_text(json.dumps({'images':{'m01-a.webp':{'file':'m01-a.webp'}}}))
            self.assertEqual(prune(root), [])
            self.assertTrue(path.is_file())


if __name__=='__main__':unittest.main()
