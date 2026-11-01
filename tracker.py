import csv
import json
import os
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

ROOT = Path(__file__).resolve().parent
FILE = ROOT / 'data' / 'prices.csv'
USAGE = ROOT / 'data' / 'api_usage.json'
FIELDS = ['checked_at','airline','price_per_person','total_price','outbound','return_flight','return_arrival','status','baggage','source']
AIRLINES = {'BR':'長榮 EVA Air','CI':'華航 China Airlines'}
OUT_DATE='2026-12-24'
RETURN_DATE='2027-01-02'
ARRIVE_DATE='2027-01-03'
MONTHLY_LIMIT=240


def load_usage():
    month=datetime.now(ZoneInfo('Asia/Taipei')).strftime('%Y-%m')
    try:
        usage=json.loads(USAGE.read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        usage={}
    if usage.get('month') != month:
        usage={'month':month,'requests':0}
    return usage


def save_usage(usage):
    USAGE.parent.mkdir(parents=True,exist_ok=True)
    USAGE.write_text(json.dumps(usage,indent=2)+'\n',encoding='utf-8')


def query(key, usage, code, **extras):
    if usage['requests'] >= MONTHLY_LIMIT:
        raise RuntimeError('MONTHLY_LIMIT_REACHED')
    params={'engine':'google_flights','api_key':key,'departure_id':'TPE','arrival_id':'LAX',
            'outbound_date':OUT_DATE,'return_date':RETURN_DATE,'type':'1','travel_class':'1',
            'adults':'2','stops':'1','currency':'TWD','gl':'tw','hl':'en','sort_by':'2',
            'include_airlines':code,**extras}
    # Reserve one request before making it; an HTTP failure may still count against quota.
    usage['requests'] += 1
    save_usage(usage)
    r=requests.get('https://serpapi.com/search.json',params=params,timeout=120)
    r.raise_for_status()
    data=r.json()
    if data.get('error'):
        raise RuntimeError(str(data['error']))
    print(f'API result {code}: status={data.get("search_metadata",{}).get("status")}, '
          f'best={len(data.get("best_flights") or [])}, other={len(data.get("other_flights") or [])}')
    return data


def choices(data):
    return (data.get('best_flights') or [])+(data.get('other_flights') or [])


def direct(item,origin,destination,day,code):
    flights=item.get('flights') or []
    if len(flights)!=1:
        return None
    f=flights[0]
    dep=f.get('departure_airport') or {}
    arr=f.get('arrival_airport') or {}
    number=str(f.get('flight_number') or '').replace(' ','').upper()
    if (dep.get('id')!=origin or arr.get('id')!=destination
            or not str(dep.get('time') or '').startswith(day)
            or not number.startswith(code)):
        return None
    return f


def record(timestamp,airline,status,price='',outbound='',returning='',arrival=''):
    return {'checked_at':timestamp,'airline':airline,
            'price_per_person':round(price/2) if isinstance(price,(int,float)) else '',
            'total_price':round(price) if isinstance(price,(int,float)) else '',
            'outbound':outbound,'return_flight':returning,'return_arrival':arrival,
            'status':status,'baggage':'UNVERIFIED','source':'SerpApi Google Flights'}


def check_airline(key,usage,code,airline,timestamp):
    print(f'Checking {airline} at {timestamp}',flush=True)
    try:
        first=query(key,usage,code)
        candidates=[x for x in choices(first)
                    if direct(x,'TPE','LAX',OUT_DATE,code) and x.get('departure_token')]
        print(f'{code}: matching outbound options with token={len(candidates)}')
        if not candidates:
            return record(timestamp,airline,'NO_OUTBOUND')
        selected=min(candidates,key=lambda x:x.get('price') if isinstance(x.get('price'),(int,float)) else float('inf'))
        outbound=direct(selected,'TPE','LAX',OUT_DATE,code)
        second=query(key,usage,code,departure_token=selected['departure_token'])
        matches=[]
        for option in choices(second):
            returning=direct(option,'LAX','TPE',RETURN_DATE,code)
            if not returning:
                continue
            arrival=str((returning.get('arrival_airport') or {}).get('time') or '')
            if not arrival.startswith(ARRIVE_DATE):
                continue
            price=option.get('price')
            if not isinstance(price,(int,float)) or price<=0:
                continue
            matches.append(record(timestamp,airline,'OK',price,
                                  outbound.get('flight_number',''),
                                  returning.get('flight_number',''),arrival))
        print(f'{code}: matching returns={len(matches)}')
        return min(matches,key=lambda x:x['total_price']) if matches else record(timestamp,airline,'NO_RETURN_MATCH')
    except Exception as exc:
        print(f'{code}: ERROR {type(exc).__name__}: {exc}',flush=True)
        return record(timestamp,airline,'QUOTA_LIMIT' if str(exc)=='MONTHLY_LIMIT_REACHED' else 'ERROR')


def run():
    key=os.getenv('SERPAPI_KEY')
    if not key:
        raise RuntimeError('Set SERPAPI_KEY in GitHub Actions Secrets')
    now=datetime.now(ZoneInfo('Asia/Taipei'))
    if now.date()>date.fromisoformat(OUT_DATE):
        print('Trip departure has passed. Stopping.')
        return
    timestamp=now.isoformat(timespec='seconds')
    usage=load_usage()
    records=[]
    for code,airline in AIRLINES.items():
        records.append(check_airline(key,usage,code,airline,timestamp))
    FILE.parent.mkdir(parents=True,exist_ok=True)
    existing=[]
    if FILE.exists():
        with FILE.open(newline='',encoding='utf-8-sig') as f:
            existing=list(csv.DictReader(f))
    existing.extend(records)
    with FILE.open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(existing)
    for item in records:
        print('Saved:',item)
    print(f'API usage for {usage["month"]}: {usage["requests"]}/{MONTHLY_LIMIT}')

if __name__=='__main__':
    run()
