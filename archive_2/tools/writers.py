"""Simple append-only data writers: no data quality columns."""
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import uuid


def utc_now():return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')


def scalar(value):
    if value is None:return None
    if hasattr(value,'ndim') and value.ndim != 0:raise ValueError('Scalar PV required')
    if hasattr(value,'item'):value=value.item()
    if isinstance(value,bytes):value=value.decode('utf-8',errors='replace')
    if isinstance(value,float) and not math.isfinite(value):return None
    if not isinstance(value,(str,int,float,bool)):raise ValueError('Scalar PV required')
    return value


def new_file(directory, label, extension):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    return directory/f'{label}_{stamp}_{os.getpid()}_{uuid.uuid4().hex[:6]}.{extension}'


class CSVWriter:
    def __init__(self, directory, subsystem, pvs):
        self.path=new_file(directory,subsystem,'csv')
        self.handle=self.path.open('x',newline='',encoding='utf-8')
        self.pvs=list(pvs);self.writer=csv.writer(self.handle)
        self.writer.writerow(['timestamp_utc',*pvs]);self.handle.flush()

    def append(self,values):
        self.writer.writerow([utc_now(),*(scalar(values.get(pv)) for pv in self.pvs)])
        self.handle.flush()

    def close(self):self.handle.close()


class JSONLWriter:
    def __init__(self,directory,label):
        self.path=new_file(directory,label,'jsonl')
        self.handle=self.path.open('x',encoding='utf-8')

    def append(self,record):
        line=json.dumps(record,allow_nan=False,separators=(',',':'))
        self.handle.write(line+'\n');self.handle.flush()
        # Burn records are infrequent: persist them at each event boundary.
        os.fsync(self.handle.fileno())

    def close(self):self.handle.close()
