# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded forecast decoding in the disposable weather worker. No GUI imports."""
import math
import time
from urllib.parse import urlencode
from yun_jin_weather import read_json,selected_location,fresh,weather_kind

FORECAST_LIMIT=96*1024
FORECAST_TTL=3600
MAX_CACHE_AGE=24*3600
HOURLY=('temperature_2m','apparent_temperature','precipitation_probability','precipitation',
        'rain','snowfall','weather_code','is_day','wind_speed_10m','wind_gusts_10m','relative_humidity_2m')
DAILY=('weather_code','temperature_2m_max','temperature_2m_min','precipitation_probability_max',
       'precipitation_sum','wind_speed_10m_max','wind_gusts_10m_max','sunrise','sunset','uv_index_max')
CURRENT=tuple(v for v in HOURLY if v!='precipitation_probability')


def valid_number(value,low=-math.inf,high=math.inf):
    return type(value) in (int,float) and math.isfinite(value) and low<=value<=high


def cleaned(key,value):
    if not valid_number(value):return None
    if key in ('weather_code','is_day'):
        if key=='is_day':return value if type(value) is int and value in (0,1) else None
        return value if type(value) is int and weather_kind(value,1) else None
    if key in ('sunrise','sunset'):return int(value) if value>0 else None
    if 'temperature' in key:bounds=(-100,70)
    elif 'probability' in key or 'humidity' in key:bounds=(0,100)
    elif 'wind_' in key:bounds=(0,450)
    elif 'uv_index' in key:bounds=(0,40)
    else:bounds=(0,3000)
    return round(value,2) if bounds[0]<=value<=bounds[1] else None


def read_forecast_json(url):return read_json(url,limit=FORECAST_LIMIT)


def fetch_forecast(location,now=None,get=read_forecast_json):
    now=time.time() if now is None else now;location=selected_location(location)
    if location is None:return None
    query=urlencode(dict(latitude=location['latitude'],longitude=location['longitude'],
        current=','.join(CURRENT),hourly=','.join(HOURLY),daily=','.join(DAILY),
        forecast_days=7,timezone='auto',timeformat='unixtime',models='best_match',
        temperature_unit='celsius',wind_speed_unit='kmh',precipitation_unit='mm'))
    data=get('https://api.open-meteo.com/v1/forecast?'+query)
    if not isinstance(data,dict) or data.get('error'):return None
    zone=data.get('timezone');offset=data.get('utc_offset_seconds')
    if not isinstance(zone,str) or not zone or len(zone)>100 or not valid_number(offset,-50400,50400):return None
    def series(name,fields,maximum,spacing):
        block=data.get(name)
        if not isinstance(block,dict):raise ValueError('Missing forecast')
        stamps=block.get('time')
        if not isinstance(stamps,list) or not 1<=len(stamps)<=maximum:raise ValueError('Invalid forecast length')
        arrays={key:block.get(key) for key in fields}
        for values in arrays.values():
            if values is not None and (not isinstance(values,list) or len(values)!=len(stamps)):
                raise ValueError('Unaligned forecast')
        result=[];previous=None
        for i,stamp in enumerate(stamps):
            if not valid_number(stamp,now-2*86400,now+9*86400):raise ValueError('Invalid timestamp')
            if previous is not None and not spacing[0]<=stamp-previous<=spacing[1]:raise ValueError('Invalid timeline')
            row={key:cleaned(key,values[i]) if values is not None else None for key,values in arrays.items()}
            row['time']=int(stamp);result.append(row);previous=stamp
        return result
    hourly=series('hourly',HOURLY,180,(3600,3600))
    daily=series('daily',DAILY,7,(23*3600,25*3600))
    current=data.get('current',{})
    if not isinstance(current,dict) or not fresh(current.get('time'),now,7200):return None
    current={**{key:cleaned(key,current.get(key)) for key in CURRENT},'time':int(current['time'])}
    return dict(schema=1,location=location,checked=now,timezone=zone,utc_offset_seconds=int(offset),
                current=current,hourly=hourly,daily=daily)


def cache_valid(data,location,now=None,ttl=MAX_CACHE_AGE):
    now=time.time() if now is None else now;location=selected_location(location)
    if not (location and isinstance(data,dict) and data.get('schema')==1
            and selected_location(data.get('location'))==location
            and valid_number(data.get('checked')) and fresh(data.get('checked'),now,ttl)
            and isinstance(data.get('timezone'),str) and 0<len(data['timezone'])<=100
            and type(data.get('utc_offset_seconds')) is int and abs(data['utc_offset_seconds'])<=50400
            and isinstance(data.get('current'),dict)):
        return False
    checked=data['checked']
    def row_valid(row,fields):
        return (isinstance(row,dict) and valid_number(row.get('time'),checked-2*86400,checked+9*86400)
                and all(row.get(k) is None or (valid_number(row[k]) and cleaned(k,row[k])==row[k]) for k in fields))
    if not row_valid(data['current'],CURRENT) or not fresh(data['current']['time'],checked,7200):return False
    for name,fields,cap,spacing in (('hourly',HOURLY,180,(3600,3600)),('daily',DAILY,7,(82800,90000))):
        rows=data.get(name)
        if not isinstance(rows,list) or not 0<len(rows)<=cap:return False
        previous=None
        for row in rows:
            if not row_valid(row,fields):return False
            if previous is not None and not spacing[0]<=row['time']-previous<=spacing[1]:return False
            previous=row['time']
    return True


def condition(row,day=None):
    code=row.get('weather_code');day=row.get('is_day') if day is None else day
    if type(code) is not int or weather_kind(code,1) is None:return 'Non disponibile',None
    rain=row.get('rain') or 0;snow=row.get('snowfall') or 0
    wind=row.get('wind_speed_10m',row.get('wind_speed_10m_max')) or 0
    if code in (61,63,65,71,73,75,80,81,82,85,86) and rain>0 and snow>0:return 'Pioggia e neve','sleet'
    if code in (0,1,2,3) and wind>=50:return 'Ventoso','wind'
    if code in (0,1):return 'Sereno','sun' if day==1 else 'clear_night' if day==0 else None
    if code==2:return 'Parzialmente nuvoloso','partly_cloudy' if day==1 else 'partly_cloudy_night' if day==0 else 'cloud'
    if code==3:return 'Nuvoloso','cloud'
    if code in (45,48):return 'Nebbia','fog'
    if code in (51,53,55):return 'Pioviggine','drizzle'
    if code in (56,57,66,67):return 'Pioggia gelata','freezing_rain'
    if code in (61,63,80,81):return 'Pioggia','rain'
    if code in (65,82):return 'Pioggia forte','heavy_rain'
    if code in (71,73,77,85):return 'Neve','snow'
    if code in (75,86):return 'Neve intensa','heavy_snow'
    if code==95:return 'Temporale','thunderstorm'
    return 'Temporale con grandine','storm_hail'
