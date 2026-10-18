# SPDX-License-Identifier: GPL-3.0-or-later
"""Stable seasonal illustrations; no image decoding until the calendar opens.

October preserves the original daily permutation exactly. November interleaves
its distinct scene groups so a stable, year-specific daily order also varies
its subject matter rather than clustering scenes from the same group.
"""
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
    tuple('abcdefg') + tuple(f'YJ-{number:03d}' for number in range(634, 689)),
    'abcdef',
)
DAILY_MONTHS = frozenset({10, 11})


def _digest(value):
    return blake2s(value.encode('utf-8'), digest_size=8).digest()


def _november_group(variant):
    """The 7 existing scenes and each G81–G88 brief form separate themes."""
    if not variant.startswith('YJ-'):
        return 'base'
    return f'G{81 + (int(variant[3:]) - 634) // 7}'


@lru_cache(maxsize=64)
def _daily_bag(year, month):
    """One year-specific permutation, computed only from IDs (never pixels)."""
    variants = VARIANTS_BY_MONTH[month - 1]
    if month != 11:
        # IMPORTANT: byte-for-byte equivalent to the published October v1
        # selection; do not change images for dates already shown to users.
        return tuple(sorted(variants, key=lambda variant: blake2s(
            f'YunJin.Calendar.Daily.v1:{year}:{month}:{variant}'.encode(),
            digest_size=8).digest()))

    groups = {}
    for variant in variants:
        groups.setdefault(_november_group(variant), []).append(variant)
    for group, members in groups.items():
        members.sort(key=lambda item: _digest(
            f'YunJin.Calendar.November.v1:{year}:{group}:{item}'))

    result = []
    previous_group = None
    for round_index in range(max(map(len, groups.values()))):
        group_order = sorted(
            (group for group, items in groups.items() if len(items) > round_index),
            key=lambda group: _digest(
                f'YunJin.Calendar.November.v1:{year}:round:{round_index}:{group}'),
        )
        # Even at round boundaries adjacent days should depict different themes.
        if len(group_order) > 1 and previous_group == group_order[0]:
            group_order.append(group_order.pop(0))
        for group in group_order:
            result.append(groups[group][round_index])
            previous_group = group
    return tuple(result)


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
