# SPDX-License-Identifier: GPL-3.0-or-later
"""Small, disposable weather worker. No GUI imports, credentials or GPS access."""
import json
import math
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

MAX_RESPONSE = 32 * 1024
WEATHER_TTL = 3600
LOCATION_TTL = 86400


def read_json(url):
    request = Request(url, headers={'User-Agent': 'Yun-Jin-Companion/1.2', 'Accept': 'application/json'})
    with urlopen(request, timeout=5) as response:
        raw = response.read(MAX_RESPONSE + 1)
    if len(raw) > MAX_RESPONSE:
        raise ValueError('Response too large')
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError('Invalid response')
    return result


def fresh(timestamp, now, ttl):
    return isinstance(timestamp, (int, float)) and math.isfinite(timestamp) and 0 <= now - timestamp < ttl


def location_valid(location):
    if not isinstance(location, dict): return False
    lat, lon = location.get('latitude'), location.get('longitude')
    return (type(lat) in (int, float) and type(lon) in (int, float)
            and math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180)


def weather_kind(code, is_day):
    if type(code) is not int or type(is_day) is not int or is_day not in (0, 1): return None
    if code in (0, 1): return 'sun' if is_day else 'clear_night'
    if code in (2, 3): return 'cloud'
    if code in (45, 48): return 'fog'
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82): return 'rain'
    if code in (71, 73, 75, 77, 85, 86): return 'snow'
    if code in (95, 96, 99): return 'storm'
    return None


def fetch_weather(location=None, now=None, get=read_json):
    now = time.time() if now is None else now
    if not (location_valid(location) and fresh(location.get('checked'), now, LOCATION_TTL)):
        data = get('https://ipwho.is/?fields=success,city,latitude,longitude')
        if data.get('success') is not True or not location_valid(data): return None
        location = {'latitude': round(data['latitude'], 2), 'longitude': round(data['longitude'], 2),
                    'city': str(data.get('city', ''))[:100], 'checked': now}
    query = urlencode({'latitude': location['latitude'], 'longitude': location['longitude'],
                       'current': 'weather_code,is_day', 'timeformat': 'unixtime', 'forecast_days': 1})
    data = get('https://api.open-meteo.com/v1/forecast?' + query).get('current', {})
    kind = weather_kind(data.get('weather_code'), data.get('is_day'))
    if not kind or not fresh(data.get('time'), now, 7200): return None
    return {'kind': kind, 'checked': now, 'observed': data['time'], 'location': location}


def main():
    result = None
    try:
        raw = sys.stdin.buffer.read(MAX_RESPONSE + 1)
        if len(raw) <= MAX_RESPONSE:
            job = json.loads(raw)
            result = fetch_weather(job.get('location'))
    except Exception:
        pass  # Offline, unavailable location and malformed replies are normal fallbacks.
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
    sys.stdout.buffer.flush()


if __name__ == '__main__': main()
