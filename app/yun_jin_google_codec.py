# SPDX-License-Identifier: GPL-3.0-or-later
"""Lossless conversion of the agenda's supported Google Calendar fields."""
from yun_jin_i18n import tr
from PyQt6.QtCore import QDateTime
from datetime import datetime, timedelta, timezone
from copy import deepcopy
from yun_jin_agenda import normalize_recurrence, wall_timestamp, local_datetime, _zone

DAYS = ('MO', 'TU', 'WE', 'TH', 'FR', 'SA', 'SU')
FIELDS = ('title', 'details', 'start_local', 'end_local', 'all_day', 'timezone', 'recurrence', 'reminder_minutes')
SCHEDULE = ('start_local', 'end_local', 'all_day', 'timezone', 'recurrence')


class UnsupportedEvent(ValueError):
    pass


def read_time(value, zone=''):
    if 'date' in value:
        return value['date'] + 'T00:00:00', True, zone
    stamp = datetime.fromisoformat(value['dateTime'].replace('Z', '+00:00'))
    tz = value.get('timeZone') or zone
    if tz:
        _zone(tz)
        if stamp.tzinfo:
            stamp = local_datetime(stamp.timestamp(), tz)
    elif stamp.tzinfo:
        # A fixed offset is not a recurring timezone. UTC preserves the instant.
        stamp, tz = stamp.astimezone(timezone.utc), 'UTC'
    return stamp.replace(tzinfo=None).isoformat(), False, tz


def write_time(stamp, all_day, zone):
    if all_day:
        return {'date': stamp[:10]}
    zone = zone or bytes(_zone('').id()).decode() or 'UTC'
    instant = wall_timestamp(stamp, zone)
    value = local_datetime(instant, zone)
    # Qt handles DST ambiguity consistently with local reminders.
    offset = _zone(zone).offsetFromUtc(QDateTime.fromSecsSinceEpoch(int(instant)))
    value = value.replace(tzinfo=timezone(timedelta(seconds=offset)))
    return {'dateTime': value.isoformat(), 'timeZone': zone}


def read_rule(lines, start, zone):
    if not lines:
        return None
    if len(lines) != 1 or not lines[0].startswith('RRULE:'):
        raise UnsupportedEvent(tr('Ricorrenza non supportata. Apri in Google Calendar.'))
    parts = dict(part.split('=', 1) for part in lines[0][6:].split(';'))
    if set(parts) - {'FREQ', 'INTERVAL', 'BYDAY', 'UNTIL', 'COUNT', 'WKST'}:
        raise UnsupportedEvent(tr('Ricorrenza non supportata. Apri in Google Calendar.'))
    frequencies = {'DAILY': 'daily', 'WEEKLY': 'weekly', 'MONTHLY': 'monthly', 'YEARLY': 'yearly'}
    if parts.get('FREQ') not in frequencies or parts.get('WKST', 'MO') != 'MO':
        raise UnsupportedEvent(tr('Ricorrenza non supportata. Apri in Google Calendar.'))
    rule = {'frequency': frequencies[parts['FREQ']], 'interval': int(parts.get('INTERVAL', 1))}
    if 'BYDAY' in parts:
        days = parts['BYDAY'].split(',')
        if rule['frequency'] != 'weekly' or any(day not in DAYS for day in days):
            raise UnsupportedEvent(tr('Ricorrenza non supportata. Apri in Google Calendar.'))
        rule['weekdays'] = [DAYS.index(day) for day in days]
    if 'COUNT' in parts:
        rule['count'] = int(parts['COUNT'])
    if 'UNTIL' in parts:
        until = parts['UNTIL']
        if len(until) == 8:
            day = datetime.strptime(until, '%Y%m%d').date()
        else:
            instant = datetime.strptime(until, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
            local = local_datetime(instant.timestamp(), zone)
            day = local.date()
            if local.time() < datetime.fromisoformat(start).time():
                day -= timedelta(days=1)
        rule['until'] = day.isoformat()
    return normalize_recurrence(rule, datetime.fromisoformat(start))


def write_rule(item):
    rule = item['recurrence']
    if not rule:
        return []
    parts = ['FREQ=' + rule['frequency'].upper(), 'INTERVAL=' + str(rule.get('interval', 1))]
    if rule['frequency'] == 'weekly':
        parts.append('BYDAY=' + ','.join(DAYS[i] for i in rule.get('weekdays', [datetime.fromisoformat(item['start_local']).weekday()])))
    if rule.get('count'):
        parts.append('COUNT=' + str(rule['count']))
    if rule.get('until'):
        if item['all_day']:
            until = rule['until'].replace('-', '')
        else:
            stamp = rule['until'] + 'T23:59:59'
            until = datetime.fromtimestamp(wall_timestamp(stamp, item['timezone']), timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        parts.append('UNTIL=' + until)
    return ['RRULE:' + ';'.join(parts)]


def decode(event, calendar_zone='UTC', default_reminders=()):
    if event.get('status') == 'cancelled':
        return None, False
    start, all_day, zone = read_time(event['start'], calendar_zone)
    end, end_all_day, _ = read_time(event['end'], zone)
    if all_day != end_all_day or end <= start:
        raise ValueError(tr('Date Google Calendar non valide.'))
    readonly = event.get('eventType', 'default') != 'default' or event.get('locked', False)
    try:
        recurrence = read_rule(event.get('recurrence', []), start, zone)
    except (UnsupportedEvent, ValueError, KeyError):
        recurrence, readonly = None, True
    reminders = event.get('reminders', {})
    # Google defaults remain untouched unless the reminder is explicitly edited.
    rules = default_reminders if reminders.get('useDefault') else reminders.get('overrides', [])
    choices = [r['minutes'] for r in rules if r.get('method') == 'popup' and isinstance(r.get('minutes'), int) and 0 <= r['minutes'] <= 43200]
    item = dict(title=event.get('summary') or tr('Impegno'), details=event.get('description', ''),
                start_local=start, end_local=end, all_day=all_day, timezone=zone,
                recurrence=recurrence, reminder_minutes=min(choices) if choices else None, exceptions={})
    if len(item['title']) > 200 or len(item['details']) > 4000 or datetime.fromisoformat(end)-datetime.fromisoformat(start) > timedelta(days=366):
        readonly = True
    return item, readonly


def encode(item, base=None):
    """PATCH only owned fields: guests, locations and other Google data survive."""
    result = {}
    if base is None or item['title'] != base['title']:
        result['summary'] = item['title']
    if base is None or item['details'] != base['details']:
        result['description'] = item['details']
    if base is None or any(item[k] != base[k] for k in SCHEDULE):
        result['start'] = write_time(item['start_local'], item['all_day'], item['timezone'])
        result['end'] = write_time(item['end_local'], item['all_day'], item['timezone'])
        result['recurrence'] = write_rule(item)
    if base is None or item['reminder_minutes'] != base['reminder_minutes']:
        result['reminders'] = {'useDefault': False, 'overrides': [] if item['reminder_minutes'] is None else [{'method': 'popup', 'minutes': item['reminder_minutes']}]}
    return result


def merge(base, local, remote):
    """Three-way field merge; a concurrent edit to a schedule is one conflict."""
    if local == remote or local == base:
        return deepcopy(remote), False
    if remote == base:
        return deepcopy(local), False
    if base is None or local is None or remote is None:
        return None, True
    result = deepcopy(remote)
    groups = [SCHEDULE, ('title',), ('details',), ('reminder_minutes',)]
    for group in groups:
        left = tuple(local[k] for k in group)
        right = tuple(remote[k] for k in group)
        before = tuple(base[k] for k in group)
        if left != before and right != before and left != right:
            return None, True
        if left != before:
            for k in group:
                result[k] = deepcopy(local[k])
    result['exceptions'] = {}
    for key in set(base.get('exceptions', {})) | set(local.get('exceptions', {})) | set(remote.get('exceptions', {})):
        before = base.get('exceptions', {}).get(key)
        left = local.get('exceptions', {}).get(key)
        right = remote.get('exceptions', {}).get(key)
        if left != before and right != before and left != right:
            return None, True
        value = left if left != before else right
        if value is not None:
            result['exceptions'][key] = deepcopy(value)
    return result, False
