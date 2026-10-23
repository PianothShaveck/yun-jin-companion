"""Complete seasonal assets, deterministic variety and bounded encoded resources."""
import hashlib
import calendar
import subprocess
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from PyQt6.QtGui import QImageReader
import yun_jin_calendar_art
from yun_jin_calendar_art import ASSETS, VARIANTS_BY_MONTH, illustration_for, variant_for


class CalendarArtTests(unittest.TestCase):
    def setUp(self):
        variant_for.cache_clear()

    def test_all_seasonal_illustrations_are_distinct_and_complete(self):
        counts = (62, 62, 62, 62, 62, 9, 9, 9, 6, 62, 62, 62)
        self.assertEqual(tuple(map(len, VARIANTS_BY_MONTH)), counts)
        expected = {
            f'm{month:02d}-{letter}.webp'
            for month, count in enumerate((6, 7, 6, 6, 7, 9, 9, 9, 6, 6, 7, 6), 1)
            for letter in 'abcdefghi'[:count]
        }
        expected.update(f'YJ-{number:03d}.webp' for number in range(85, 363))
        expected.update(f'YJ-{number:03d}.webp' for number in range(578, 745))
        paths = list(ASSETS.glob('*.webp'))
        self.assertEqual({p.name for p in paths}, expected)
        self.assertEqual(len({hashlib.sha256(p.read_bytes()).digest() for p in paths}), 529)
        for path in paths:
            reader = QImageReader(str(path))
            size = reader.size()
            self.assertGreaterEqual(size.width(), 1000, path.name)
            self.assertLessEqual(size.width(), 1536, path.name)
            self.assertGreaterEqual(size.height(), 600, path.name)
            self.assertLessEqual(size.height(), 1024, path.name)
            self.assertLess(abs(size.width() / size.height() - 1.5), 0.003, path.name)
            self.assertFalse(reader.read().isNull(), path.name)
        self.assertLess(sum(p.stat().st_size for p in paths), 800 * 1024 * 1024)

    def test_all_supported_years_use_complete_bags_without_adjacent_repeats(self):
        for month in range(1, 13):
            if month in yun_jin_calendar_art.DAILY_MONTHS:continue
            variants = VARIANTS_BY_MONTH[month - 1]
            count = len(variants)
            choices = [variant_for(year, month) for year in range(1, 10000)]
            for start in range(0, len(choices) - count + 1, count):
                self.assertEqual(set(choices[start:start + count]), set(variants), (month, start + 1))
            for year, (previous, current) in enumerate(zip(choices, choices[1:]), 2):
                self.assertNotEqual(previous, current, (year, month))
            remainder = len(choices) % count
            if remainder:
                self.assertEqual(len(set(choices[-remainder:])), remainder, month)

    def test_selection_is_stable_seasonal_and_independent_of_request_order(self):
        dates = [
            (year, month)
            for year in (1, 5, 6, 2026, 2030, 2031, 9995, 9996, 9999)
            for month in range(1, 13)
        ]
        expected = {date: variant_for(*date) for date in dates}
        variant_for.cache_clear()
        for year, month in reversed(dates):
            choice = variant_for(year, month)
            self.assertEqual(choice, expected[year, month])
            expected_file = f'{choice}.webp' if choice.startswith('YJ-') else f'm{month:02d}-{choice}.webp'
            self.assertEqual(illustration_for(year, month), ASSETS.parent / 'calendar-preview' / expected_file)

    def test_winter_days_are_distinct_seasonal_varied_and_reach_every_scene(self):
        for month, start, stop in ((1, 85, 141), (2, 141, 196), (12, 689, 745)):
            pool = set(VARIANTS_BY_MONTH[month - 1]); seen = set(); previous = None
            for year in range(1, 10000):
                count = calendar.monthrange(year, month)[1]
                choices = tuple(variant_for(year, month, day) for day in range(1, count + 1))
                self.assertEqual(len(set(choices)), count, (year, month))
                self.assertTrue(set(choices) <= pool, (year, month))
                self.assertNotEqual(choices, previous, (year, month))
                # Brief groups are seven scenes each; base scenes form one group.
                groups = [None if not item.startswith('YJ-') else (int(item[3:]) - start) // 7
                          for item in choices]
                self.assertTrue(all(a != b for a, b in zip(groups, groups[1:])), (year, month))
                seen.update(choices); previous = choices
            self.assertEqual(seen, pool)
            new_ids = {f'YJ-{number:03d}' for number in range(start, stop)}
            self.assertTrue(new_ids <= seen)
            for other_month in range(1, 13):
                if other_month != month:
                    self.assertTrue(new_ids.isdisjoint(VARIANTS_BY_MONTH[other_month - 1]))
        for leap_year in (2000, 2032, 2400):
            self.assertNotEqual(illustration_for(leap_year, 2, 28), illustration_for(leap_year, 2, 29))
        for common_year in (2026, 2100, 2200):
            with self.assertRaises(ValueError): illustration_for(common_year, 2, 29)

    def test_spring_days_are_distinct_and_interleave_themes_across_years(self):
        for month, start in ((3, 196), (4, 252), (5, 308)):
            pool = set(VARIANTS_BY_MONTH[month - 1]); seen = set(); previous = None
            for year in range(1, 10000):
                count = calendar.monthrange(year, month)[1]
                choices = tuple(variant_for(year, month, day) for day in range(1, count + 1))
                self.assertEqual(len(set(choices)), count, (year, month))
                self.assertTrue(set(choices) <= pool, (year, month))
                self.assertNotEqual(choices, previous, (year, month))
                groups = [None if not item.startswith('YJ-') else (int(item[3:]) - start) // 7
                          for item in choices]
                self.assertTrue(all(a != b for a, b in zip(groups, groups[1:])), (year, month))
                seen.update(choices); previous = choices
            self.assertEqual(seen, pool)

    def test_published_winter_mapping_is_exactly_preserved(self):
        # Captured from 1.5.5 commit 1638621272 before adding spring assets.
        for month, expected in (
            (1, '2c956e72f55bc8b3025bb8ee52b47deb40808266641ddf0791088eedff3e8387'),
            (2, '3ef5bce8b1784b368404eb1bc622d7d4b27fa42afd255535952284d17323fc9e'),
            (12, '3ed9e33f3f216d53ff95acc9db980d88000904fe6969e1f26746e5768b6969da'),
        ):
            digest = hashlib.sha256()
            for year in range(1, 10000):
                for day in range(1, calendar.monthrange(year, month)[1] + 1):
                    digest.update(f'{year}:{month}:{day}:{variant_for(year, month, day)}\n'.encode())
            self.assertEqual(digest.hexdigest(), expected, month)

    def test_winter_order_survives_cache_clear_restart_and_hash_randomization(self):
        dates = [(year, month, day) for year in (1, 2026, 2032, 9999)
                 for month in (1, 2, 3, 4, 5, 12) for day in (1, 15, 28)]
        expected = [str(illustration_for(*day)) for day in dates]
        variant_for.cache_clear(); yun_jin_calendar_art._daily_bag.cache_clear()
        self.assertEqual([str(illustration_for(*day)) for day in reversed(dates)], list(reversed(expected)))
        script = ('import json,sys;sys.path.insert(0,sys.argv[1]);'
                  'from yun_jin_calendar_art import illustration_for;'
                  f'print(json.dumps([str(illustration_for(*day)) for day in {dates!r}]))')
        import json
        for seed in ('1', '98765'):
            output = subprocess.check_output([sys.executable, '-c', script, str(ASSETS.parent.parent)],
                                             env=dict(os.environ, PYTHONHASHSEED=seed), text=True)
            self.assertEqual(json.loads(output), expected)

    def test_published_october_and_november_mapping_is_exactly_preserved(self):
        # Captured from published commit 982205d before introducing winter days.
        for month, count, expected in (
            (10, 31, '1a24a03948d697f92f4817bc5763763f5ff964bb325b3342e796a3b3de7fa697'),
            (11, 30, '5d6ce4b4b310f0482c045247cd1b96974697ba6584955ae0e480ddbc6d6e9c92'),
        ):
            digest = hashlib.sha256()
            for year in range(1, 10000):
                for day in range(1, count + 1):
                    digest.update(f'{year}:{month}:{day}:{variant_for(year, month, day)}\n'.encode())
            self.assertEqual(digest.hexdigest(), expected, month)

    def test_calendar_has_no_fixed_short_cycle(self):
        years = {
            year: tuple(variant_for(year, month) for month in range(1, 13))
            for year in range(2001, 2101)
        }
        for cycle in (2, 3, 5, 6, 7, 9):
            self.assertTrue(any(years[year] != years[year + cycle] for year in range(2001, 2101 - cycle)), cycle)

    def test_every_october_has_31_distinct_images_in_a_year_specific_order(self):
        pool=set(VARIANTS_BY_MONTH[9]);seen=set();previous=None
        for year in range(1,10000):
            choices=tuple(variant_for(year,10,day) for day in range(1,32))
            self.assertEqual(len(set(choices)),31,year)
            self.assertTrue(set(choices)<=pool,year)
            self.assertNotEqual(choices,previous,year)
            seen.update(choices);previous=choices
        self.assertEqual(seen,pool)
        expected=[illustration_for(2060,10,day) for day in range(1,32)]
        variant_for.cache_clear();yun_jin_calendar_art._daily_bag.cache_clear()
        for day in range(31,0,-1):self.assertEqual(illustration_for(2060,10,day),expected[day-1])
        self.assertNotEqual(expected,[illustration_for(2026,10,day) for day in range(1,32)])

    def test_every_november_has_thirty_distinct_images_and_interleaved_scenes(self):
        pool = set(VARIANTS_BY_MONTH[10]); all_seen = set(); previous = None
        self.assertEqual(yun_jin_calendar_art.DAILY_MONTHS, frozenset({1, 2, 3, 4, 5, 10, 11, 12}))
        self.assertEqual(len(pool), 62)
        for year in range(1, 10000):
            choices = tuple(variant_for(year, 11, day) for day in range(1, 31))
            self.assertEqual(len(set(choices)), 30, year)
            self.assertTrue(set(choices) <= pool, year)
            self.assertNotEqual(choices, previous, year)
            groups = tuple(yun_jin_calendar_art._november_group(choice) for choice in choices)
            self.assertTrue(all(a != b for a, b in zip(groups, groups[1:])), year)
            all_seen.update(choices); previous = choices
        self.assertEqual(all_seen, pool)
        expected = tuple(illustration_for(2060, 11, day) for day in range(1, 31))
        variant_for.cache_clear(); yun_jin_calendar_art._daily_bag.cache_clear()
        for day in range(30, 0, -1):
            self.assertEqual(illustration_for(2060, 11, day), expected[day-1])
            self.assertTrue(expected[day-1].is_file())
        self.assertNotEqual(expected, tuple(illustration_for(2026, 11, day) for day in range(1, 31)))

    def test_frozen_october_and_remaining_monthly_examples_are_unchanged(self):
        # Frozen examples from the actual published 1.5.3 algorithm.
        for year, day, expected in [
            (2026, 1, 'YJ-596'), (2026, 8, 'YJ-581'),
            (2026, 15, 'YJ-584'), (2026, 30, 'YJ-615'),
            (2027, 1, 'YJ-625'), (2027, 8, 'YJ-617'),
            (2060, 1, 'YJ-606'), (2060, 15, 'YJ-624'),
            (9999, 1, 'YJ-589'), (9999, 30, 'YJ-609'),
        ]:
            self.assertEqual(variant_for(year, 10, day), expected)
        for year, month, expected in [
            (2026, 9, 'c'), (9999, 8, 'b'),
        ]:
            for day in (1, 15, 28):
                self.assertEqual(variant_for(year, month, day), expected)

    def test_daily_work_is_bounded(self):
        yun_jin_calendar_art._daily_bag.cache_clear()
        with patch.object(yun_jin_calendar_art,'blake2s',wraps=hashlib.blake2s) as digest:
            for day in range(1,32):variant_for(2060,10,day)
            self.assertLessEqual(digest.call_count,62)
        for year in range(1,301):variant_for(year,10,1)
        yun_jin_calendar_art._daily_bag.cache_clear()
        variant_for.cache_clear()
        with patch.object(yun_jin_calendar_art, 'blake2s', wraps=hashlib.blake2s) as digest:
            for day in range(1, 31): variant_for(2060, 11, day)
            self.assertLessEqual(digest.call_count, 150)
        for month in (1, 2, 3, 4, 5, 12):
            variant_for.cache_clear(); yun_jin_calendar_art._daily_bag.cache_clear()
            with patch.object(yun_jin_calendar_art, 'blake2s', wraps=hashlib.blake2s) as digest:
                for day in range(1, calendar.monthrange(2060, month)[1] + 1):
                    variant_for(2060, month, day)
                self.assertLessEqual(digest.call_count, 150)
            for year in range(1, 301): variant_for(year, month, 1)
        self.assertLessEqual(yun_jin_calendar_art._daily_bag.cache_info().currsize,64)
        for year,month,day in [(2026,10,0),(2026,10,32),(2026,11,0),(2026,11,31),(2026,2,29),(2026,4,31)]:
            with self.assertRaises(ValueError):illustration_for(year,month,day)

    def test_late_year_selection_has_bounded_work_and_cache(self):
        with patch.object(yun_jin_calendar_art, 'blake2s', wraps=hashlib.blake2s) as digest:
            choice = variant_for(9999, 8)
            self.assertIn(choice, VARIANTS_BY_MONTH[7])
            self.assertLessEqual(digest.call_count, 18)
            count = digest.call_count
            self.assertEqual(variant_for(9999, 8), choice)
            self.assertEqual(digest.call_count, count)
        for year in range(1, 401):
            variant_for(year, 1)
        info = variant_for.cache_info()
        self.assertEqual(info.maxsize, 256)
        self.assertEqual(info.currsize, 256)

    def test_invalid_years_and_months_are_rejected(self):
        for year, month in ((0, 1), (10000, 1), (2026, 0), (2026, 13)):
            with self.subTest(year=year, month=month):
                with self.assertRaises(ValueError):
                    variant_for(year, month)
                with self.assertRaises(ValueError):
                    illustration_for(year, month)


if __name__ == '__main__':
    unittest.main(verbosity=2)
