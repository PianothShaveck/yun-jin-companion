# SPDX-License-Identifier: GPL-3.0-or-later
"""Stable seasonal illustrations; no image decoding until the calendar opens."""
from functools import lru_cache
from datetime import date
from hashlib import blake2s
from pathlib import Path

ASSETS = Path(__file__).resolve().parent / 'assets' / 'calendar'
VARIANTS_BY_MONTH = (
    tuple('abcdef') + tuple(f'YJ-{number:03d}' for number in range(85, 113)),
    'abcdefg', 'abcdef', 'abcdef', 'abcdefg', 'abcdefghi',
    'abcdefghi', 'abcdefghi', 'abcdef',
    tuple('abcdef') + tuple(f'YJ-{number:03d}' for number in range(578, 634)),
    'abcdefg', 'abcdef',
)
DAILY_MONTHS = frozenset({10})


@lru_cache(maxsize=64)
def _daily_bag(year, month):
    """One independent permutation per year, without decoding any artwork."""
    return tuple(sorted(VARIANTS_BY_MONTH[month - 1], key=lambda variant: blake2s(
        f'YunJin.Calendar.Daily.v1:{year}:{month}:{variant}'.encode(),
        digest_size=8).digest()))


def _raw_bag(month, block):
    return sorted(
        VARIANTS_BY_MONTH[month - 1],
        key=lambda letter: blake2s(
            f'YunJin.Calendar.v2:{month}:{block}:{letter}'.encode(),
            digest_size=8,
        ).digest(),
    )


@lru_cache(maxsize=256)
def variant_for(year, month, day=1):
    date(year, month, day)  # Also reject nonexistent days, including leap dates.
    if month in DAILY_MONTHS:
        return _daily_bag(year, month)[day - 1]
    # Each block uses every picture for this month in a fresh stable order.
    # Swapping only the first two entries preserves the last entry, so checking
    # the previous raw bag also prevents repeats across block boundaries.
    block, index = divmod(year - 1, len(VARIANTS_BY_MONTH[month - 1]))
    bag = _raw_bag(month, block)
    if block and bag[0] == _raw_bag(month, block - 1)[-1]:
        bag[0], bag[1] = bag[1], bag[0]
    return bag[index]


def illustration_for(year, month, day=1):
    variant = variant_for(year, month, day)
    # New catalog IDs stay recognizable across source briefs and release files.
    name = variant if variant.startswith('YJ-') else f'm{month:02d}-{variant}'
    return ASSETS / f'{name}.webp'
