"""Read simple-archiver CSV history without blocking the recording loop."""
import asyncio
from collections import deque
import csv
from datetime import datetime, timezone, timedelta
import math

MAX_POINTS = 10000


def read_history(directory, pv, hours, offset, now=None):
    end = (now or datetime.now(timezone.utc)) - timedelta(hours=offset)
    start = end - timedelta(hours=hours)
    points = deque(maxlen=MAX_POINTS)
    count = 0
    for path in sorted(directory.glob('slow_controls_*.csv')):
        with path.open(newline='', encoding='utf-8') as handle:
            reader = csv.DictReader(handle)
            if pv not in (reader.fieldnames or []):
                continue
            for row in reader:
                try:
                    when = datetime.fromisoformat(row['timestamp_utc'].replace('Z', '+00:00'))
                    if when.tzinfo is None or not start <= when <= end:
                        continue
                    text = row[pv]
                    value = float(text) if text else float('nan')
                except (ValueError, TypeError, KeyError):
                    continue
                points.append((when, value))
                count += 1
    # File names are UTC start times. Sort retained rows for overlapping runs.
    points = sorted(points)
    x = [(when-end).total_seconds()/3600 for when, value in points]
    y = [value for when, value in points]
    return x, y, count, start, end


class HistoryControls:
    def __init__(self, builder, prefix, directory, default_pv):
        self.directory = directory
        self.busy = False
        self.channel = builder.stringOut(prefix+':HistoryPV', initial_value=default_pv)
        self.hours = builder.aOut(prefix+':HistoryHours', initial_value=1, EGU='h',
                                  validate=lambda record, v: math.isfinite(v) and v > 0)
        self.offset = builder.aOut(prefix+':HistoryOffsetHours', initial_value=0, EGU='h',
                                   validate=lambda record, v: math.isfinite(v) and v >= 0)
        self.status = builder.stringIn(prefix+':HistoryStatus', initial_value='Choose channel, then Load')
        self.start = builder.stringIn(prefix+':HistoryStartUTC', initial_value='')
        self.end = builder.stringIn(prefix+':HistoryEndUTC', initial_value='')
        self.x = builder.WaveformIn(prefix+':HistoryX', initial_value=[0.0], length=MAX_POINTS)
        self.y = builder.WaveformIn(prefix+':HistoryY', initial_value=[float('nan')], length=MAX_POINTS)
        self.load = builder.boolOut(prefix+':HistoryLoad', initial_value=False,
                                    on_update=self.load_history, always_update=True)

    async def load_history(self, value):
        if not value or self.busy:
            return
        self.busy = True
        self.status.set('Loading...')
        # Clear previous trace so errors/empty results cannot show old data.
        self.x.set([0.0])
        self.y.set([float('nan')])
        try:
            pv = str(self.channel.get()).strip()
            hours, offset = float(self.hours.get()), float(self.offset.get())
            x, y, count, start, end = await asyncio.to_thread(
                read_history, self.directory, pv, hours, offset)
            self.start.set(start.isoformat(timespec='seconds'))
            self.end.set(end.isoformat(timespec='seconds'))
            self.x.set(x or [0.0])
            self.y.set(y or [float('nan')])
            self.status.set((f'{len(x)} rows' if count <= MAX_POINTS else f'Last {MAX_POINTS} of {count} rows') if count else 'No data in selected window')
        except Exception as exc:
            self.status.set('History read failed; see console')
            print(f'History read failed: {exc}', flush=True)
        finally:
            self.busy = False
            self.load.set(False)
