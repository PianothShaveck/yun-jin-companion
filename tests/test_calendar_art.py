"""Complete seasonal assets, deterministic variety and bounded encoded resources."""
import hashlib
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
        counts = (34, 7, 6, 6, 7, 9, 9, 9, 6, 6, 7, 6)
        self.assertEqual(tuple(map(len, VARIANTS_BY_MONTH)), counts)
        expected = {
            f'm{month:02d}-{letter}.webp'
            for month, count in enumerate((6, 7, 6, 6, 7, 9, 9, 9, 6, 6, 7, 6), 1)
            for letter in 'abcdefghi'[:count]
        }
        expected.update(f'YJ-{number:03d}.webp' for number in range(85, 113))
        paths = list(ASSETS.glob('*.webp'))
        self.assertEqual({p.name for p in paths}, expected)
        self.assertEqual(len({hashlib.sha256(p.read_bytes()).digest() for p in paths}), 112)
        for path in paths:
            reader = QImageReader(str(path))
            size = reader.size()
            self.assertGreaterEqual(size.width(), 1000, path.name)
            self.assertLessEqual(size.width(), 1536, path.name)
            self.assertGreaterEqual(size.height(), 600, path.name)
            self.assertLessEqual(size.height(), 1024, path.name)
            self.assertLess(abs(size.width() / size.height() - 1.5), 0.003, path.name)
            self.assertFalse(reader.read().isNull(), path.name)
        self.assertLess(sum(p.stat().st_size for p in paths), 95 * 1024 * 1024)

    def test_all_supported_years_use_complete_bags_without_adjacent_repeats(self):
        for month in range(1, 13):
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
            self.assertEqual(illustration_for(year, month), ASSETS / expected_file)

    def test_new_briefs_are_all_reachable_only_in_january(self):
        new_ids = {f'YJ-{number:03d}' for number in range(85, 113)}
        january = {illustration_for(year, 1).stem for year in range(1, 35)}
        self.assertTrue(new_ids.issubset(january))
        for month in range(2, 13):
            self.assertTrue(new_ids.isdisjoint(VARIANTS_BY_MONTH[month - 1]))

    def test_calendar_has_no_fixed_short_cycle(self):
        years = {
            year: tuple(variant_for(year, month) for month in range(1, 13))
            for year in range(2001, 2101)
        }
        for cycle in (2, 3, 5, 6, 7, 9):
            self.assertTrue(any(years[year] != years[year + cycle] for year in range(2001, 2101 - cycle)), cycle)

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
