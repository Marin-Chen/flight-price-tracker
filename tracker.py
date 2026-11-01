import csv
import os
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

ROOT = Path(__file__).resolve().parent
FILE = ROOT / 'data' / 'prices.csv'
FIELDS = ['checked_at','airline','price_per_person','total_price','outbound','return_flight','return_arrival','status','baggage','source']
AIRLINES = {'BR':'長榮 EVA Air','CI':'華航 China Airlines','JX':'星宇 STARLUX'}
OUT_DATE='2026-12-24'
RETURN_DATE='2027-01-02'
ARRIVE_DATE='2027-01-03'


def query(key, **extras):
    params = {'engine':'google_flights','api_key':key,'departure_id':'TPE','arrival_id':'LAX',
              'outbound_date':OUT_DATE,'return_date':RETURN_DATE,'type':'1','travel_class':'1',
              'adults':'2','stops':'1','currency':'TWD','gl':'tw','hl':'en','sort_by':'2',
              'include_airlines':extras.pop('airline'), **extras}
    r=requests.get('https://serpapi.com/search.json',params=params,timeout=120)
    r.raise_for_status()
    data=r.json()
    if data.get('error'):
        raise RuntimeError(data['error'])
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


def run():
    key=os.getenv('SERPAPI_KEY')
    if not key:
        raise RuntimeError('Set SERPAPI_KEY in GitHub Actions Secrets')
    now=datetime.now(ZoneInfo('Asia/Taipei'))
    if now.date()>date.fromisoformat(OUT_DATE):
        print('Trip departure has passed. Stopping.')
        return
    # One airline per run, rotating by Taiwan local 8/14/20 schedule.
    slot={8:0,14:1,20:2}.get(now.hour,now.timetuple().tm_yday % 3)
    code=list(AIRLINES)[slot]
    airline=AIRLINES[code]
    timestamp=now.isoformat(timespec='seconds')
    print('Checking',airline,'at',timestamp)
    # Exactly one initial query, and at most one return selection query.
    first=query(key,airline=code)
    candidates=[x for x in choices(first) if direct(x,'TPE','LAX',OUT_DATE,code) and x.get('departure_token')]
    records=[]
    if candidates:
        # Cheapest returned outbound option with selection token.
        selected=min(candidates,key=lambda x: x.get('price') if isinstance(x.get('price'),(int,float)) else float('inf'))
        outbound=direct(selected,'TPE','LAX',OUT_DATE,code)
        second=query(key,airline=code,departure_token=selected['departure_token'])
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
            records.append({'checked_at':timestamp,'airline':airline,
                'price_per_person':round(price/2), 'total_price':round(price),
                'outbound':outbound.get('flight_number',''),
                'return_flight':returning.get('flight_number',''),
                'return_arrival':arrival,'status':'OK',
                'baggage':'UNVERIFIED','source':'SerpApi Google Flights'})
    if not records:
        records=[{'checked_at':timestamp,'airline':airline,'price_per_person':'',
            'total_price':'','outbound':'','return_flight':'','return_arrival':'',
            'status':'NO_MATCH','baggage':'UNVERIFIED','source':'SerpApi Google Flights'}]
    FILE.parent.mkdir(parents=True,exist_ok=True)
    existing=[]
    if FILE.exists():
        with FILE.open(newline='',encoding='utf-8-sig') as f:
            existing=list(csv.DictReader(f))
    # Only store the minimum verified-date result for this query, never fabricate missing fares.
    best=min(records,key=lambda r: r['total_price'] if isinstance(r['total_price'],int) else float('inf'))
    existing.append(best)
    with FILE.open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(existing)
    print('Saved:',best)

if __name__=='__main__':
    run()
