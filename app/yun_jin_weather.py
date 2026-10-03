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


def selected_location(location):
    """Keep only bounded, validated fields from a selected search result."""
    if not location_valid(location): return None
    city=location.get('city')
    if not isinstance(city,str) or not city.strip(): return None
    result={'latitude':round(location['latitude'],5),'longitude':round(location['longitude'],5),
            'city':' '.join(city.split())[:100]}
    for key in ('region','country'):
        value=location.get(key,'')
        result[key]=' '.join(value.split())[:100] if isinstance(value,str) else ''
    return result


def location_label(location):
    return ' · '.join(dict.fromkeys(location.get(key,'') for key in ('city','region','country')
                                   if location.get(key)))


def search_cities(name,get=read_json):
    if not isinstance(name,str): return []
    name=' '.join(name.split())
    if not 2<=len(name)<=100:return []
    query=urlencode({'name':name,'count':10,'language':'it','format':'json'})
    data=get('https://geocoding-api.open-meteo.com/v1/search?'+query)
    if data.get('error'):raise ValueError('Geocoding unavailable')
    rows=data.get('results',[])
    if not isinstance(rows,list):raise ValueError('Invalid search results')
    results=[];seen=set()
    for row in rows[:10]:
        if not isinstance(row,dict):continue
        location=selected_location({'city':row.get('name'),'region':row.get('admin1'),
                                    'country':row.get('country'),'latitude':row.get('latitude'),
                                    'longitude':row.get('longitude')})
        if location:
            key=(location['city'],location['latitude'],location['longitude'])
            if key not in seen:results.append(location);seen.add(key)
    return results


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
    location=selected_location(location)
    if location is None:return None
    location=dict(location,source='manual')
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
            if job.get('operation')=='cities':
                result={'cities':search_cities(job.get('name'))}
            else:
                result = fetch_weather(job.get('location'))
    except Exception:
        pass  # Offline, unavailable location and malformed replies are normal fallbacks.
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode('utf-8'))
    sys.stdout.buffer.flush()


if __name__ == '__main__': main()
