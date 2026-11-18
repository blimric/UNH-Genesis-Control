"""On-demand history reads from this subsystem's saved data."""
import asyncio
from collections import deque
import csv
from datetime import datetime,timezone,timedelta
import json
import math
from pathlib import Path

LIMIT=10000


def read_csv(directory,subsystem,pv,hours,offset,now=None):
    end=(now or datetime.now(timezone.utc))-timedelta(hours=offset);start=end-timedelta(hours=hours)
    points=deque(maxlen=LIMIT);total=0
    for path in sorted(Path(directory).glob(f'{subsystem}_*.csv')):
        with path.open(newline='',encoding='utf-8') as handle:
            reader=csv.DictReader(handle)
            if pv not in (reader.fieldnames or []):continue
            for row in reader:
                try:
                    stamp=datetime.fromisoformat(row['timestamp_utc'].replace('Z','+00:00'))
                    if stamp.tzinfo is None or not start<=stamp<=end:continue
                    value=float(row[pv]) if row[pv] else float('nan')
                except (ValueError,TypeError,KeyError):continue
                points.append((stamp,value));total+=1
    points=sorted(points)
    return [(t-end).total_seconds()/3600 for t,v in points],[v for t,v in points],total,start,end


def read_burn(directory,index=0):
    """0 selects the latest observed burn; negative indexes are rejected."""
    if index<0:raise ValueError('Burn index must be nonnegative')
    # Keep the latest finished/started entry per burn and sort by start time.
    burns={}
    for path in sorted(Path(directory).glob('ssrf_burns_*.jsonl')):
        with path.open(encoding='utf-8') as handle:
            for line in handle:
                try:row=json.loads(line)
                except json.JSONDecodeError:continue # an interrupted final line
                if row.get('burn_id'):burns[row['burn_id']]=row
    rows=list(reversed(sorted(burns.values(),key=lambda row:row.get('started_utc',''))))
    if index>=len(rows):raise ValueError('No burn at selected index')
    return rows[index]


class History:
    def __init__(self,builder,config):
        p=config['control_prefix'];self.cfg=config;self.busy=False;self.burn_busy=False
        self.channel=builder.stringOut(p+':HistoryPV',initial_value=config['pvs'][0])
        self.hours=builder.aOut(p+':HistoryHours',initial_value=1,validate=lambda r,v:math.isfinite(v) and v>0)
        self.offset=builder.aOut(p+':HistoryOffsetHours',initial_value=0,validate=lambda r,v:math.isfinite(v) and v>=0)
        self.status=builder.stringIn(p+':HistoryStatus',initial_value='Select channel; Load')
        self.start=builder.stringIn(p+':HistoryStartUTC',initial_value='')
        self.end=builder.stringIn(p+':HistoryEndUTC',initial_value='')
        self.x=builder.WaveformIn(p+':HistoryX',initial_value=[0.0],length=LIMIT)
        self.y=builder.WaveformIn(p+':HistoryY',initial_value=[float('nan')],length=LIMIT)
        self.load=builder.boolOut(p+':HistoryLoad',on_update=self.refresh,always_update=True)
        if config['subsystem']=='ssrf':
            self.index=builder.longOut(p+':BurnIndex',initial_value=0,validate=lambda r,v:v>=0)
            self.burn_status=builder.stringIn(p+':BurnStatus',initial_value='0 = most recent burn')
            self.burn_id=builder.stringIn(p+':BurnID',initial_value='')
            self.burn_time=builder.stringIn(p+':BurnStartUTC',initial_value='')
            n=int(config.get('burn_logging',{}).get('sample_count',8192))
            self.bx=builder.WaveformIn(p+':BurnX',initial_value=[0.0],length=n)
            self.by=builder.WaveformIn(p+':BurnY',initial_value=[float('nan')],length=n)
            self.burn_load=builder.boolOut(p+':BurnLoad',on_update=self.refresh_burn,always_update=True)

    async def refresh(self,value):
        if not value or self.busy:return
        self.busy=True;self.status.set('Loading...');self.x.set([0.0]);self.y.set([float('nan')])
        try:
            args=(self.cfg['output'],self.cfg['subsystem'],str(self.channel.get()),float(self.hours.get()),float(self.offset.get()))
            x,y,total,start,end=await asyncio.to_thread(read_csv,*args)
            self.start.set(start.isoformat(timespec='seconds'));self.end.set(end.isoformat(timespec='seconds'))
            self.x.set(x or [0.0]);self.y.set(y or [float('nan')])
            self.status.set(f'{len(x)} of {total} rows' if total else 'No data in selected window')
        except Exception as exc:self.status.set(str(exc)[:39])
        finally:self.busy=False;self.load.set(False)

    async def refresh_burn(self,value):
        if not value or self.burn_busy:return
        self.burn_busy=True;self.burn_status.set('Loading...');self.bx.set([0.0]);self.by.set([float('nan')]);self.burn_id.set('');self.burn_time.set('')
        try:
            row=await asyncio.to_thread(read_burn,self.cfg['output']/'burns',int(self.index.get()))
            wave=row.get('waveform')
            self.burn_id.set(row['burn_id']);self.burn_time.set(row['started_utc'])
            if not wave:raise ValueError('No waveform saved for this burn')
            values=wave['values'];dt=wave['sample_interval_s']
            # History waveform capacity is fixed at IOC initialization.
            limit=int(self.cfg.get('burn_logging',{}).get('sample_count',8192))
            if len(values)>limit:raise ValueError('Waveform exceeds display capacity')
            self.bx.set([i*dt for i in range(len(values))]);self.by.set(values)
            self.burn_status.set(str(row.get('outcome',''))[:39])
        except Exception as exc:self.burn_status.set(str(exc)[:39])
        finally:self.burn_busy=False;self.burn_load.set(False)
