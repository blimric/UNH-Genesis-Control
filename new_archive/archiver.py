"""Simple Genesis CSV recorder, inspired by J. Maxwell's softioc_toolkit archiver.
Uses read-only aioca monitors and a periodic CSV writer; see LICENSE.
"""
import argparse
import asyncio
import csv
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import signal
import sys
import yaml


def load_settings(path):
    path = Path(path).resolve()
    config = yaml.safe_load(path.read_text())
    interval = float(config.get('save_interval_s', 1.0))
    if not math.isfinite(interval) or interval <= 0:
        raise ValueError('save_interval_s must be a positive finite number')
    pvs = []
    for filename in config['pv_files']:
        data = yaml.safe_load((path.parent / filename).read_text())
        for pv in data['pvs']:
            if not isinstance(pv, str) or not pv.strip() or pv != pv.strip():
                raise ValueError(f'Invalid PV name: {pv!r}')
            if pv in pvs:
                raise ValueError(f'Duplicate PV: {pv}')
            pvs.append(pv)
    if not pvs:
        raise ValueError('No PVs configured')
    output = (path.parent / config['output_directory']).resolve()
    return config, interval, pvs, output


class SaveInterval:
    def __init__(self, seconds, wake):
        self.seconds = float(seconds)
        self.wake = wake

    @staticmethod
    def valid(record, value):
        return math.isfinite(value) and value > 0

    def update(self, value):
        if not self.valid(None, value):
            raise ValueError('Save interval must be positive and finite')
        self.seconds = float(value)
        self.wake.set()


def start_interval_pv(config, interval, loop, output=None, pvs=None):
    from softioc import builder, softioc, asyncio_dispatcher
    os.environ['EPICS_CA_SERVER_PORT'] = str(config.get('interval_pv_port', 5140))
    name = config.get('interval_pv', 'UNH:GEN:ARCH:SaveInterval')
    record = builder.aOut(
        name, initial_value=interval.seconds, EGU='s', PREC=3,
        DESC='Time between CSV saves', validate=interval.valid, on_update=interval.update,
        always_update=True,
    )
    from history import HistoryControls
    history = HistoryControls(builder, config.get("control_prefix", "UNH:GEN:ARCH"), output, pvs[0])
    builder.LoadDatabase()
    dispatcher = asyncio_dispatcher.AsyncioDispatcher(loop=loop)
    softioc.iocInit(dispatcher, enable_pva=False)
    print(f'Save interval PV: {name} = {interval.seconds:g} seconds', flush=True)
    return record, dispatcher, history


class CSVRecorder:
    def __init__(self, output, pvs):
        output.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
        self.path = output / f'slow_controls_{stamp}_{os.getpid()}.csv'
        self.pvs = pvs
        self.latest = dict.fromkeys(pvs, '')
        self.file = self.path.open('x', newline='', encoding='utf-8')
        self.writer = csv.writer(self.file)
        self.writer.writerow(['timestamp_utc', *pvs])
        self.file.flush()

    def update(self, pv, raw):
        if raw is None or not getattr(raw, 'ok', True):
            self.latest[pv] = ''
            return
        value = getattr(raw, 'value', raw)
        if getattr(value, 'ndim', 0) != 0:
            raise ValueError(f'Expected scalar for {pv}')
        if hasattr(value, 'item'):
            value = value.item()
        if isinstance(value, bytes):
            value = value.decode('utf-8', errors='replace')
        if not isinstance(value, (str, int, float, bool)):
            raise ValueError(f'Unsupported value for {pv}: {type(value).__name__}')
        self.latest[pv] = value

    def snapshot(self):
        stamp = datetime.now(timezone.utc).isoformat(timespec='milliseconds')
        self.writer.writerow([stamp, *(self.latest[pv] for pv in self.pvs)])
        self.file.flush()

    def close(self):
        self.file.close()


async def run(config, interval, pvs, output):
    # Configure CA before importing aioca/libca.
    addresses = config.get('epics_ca_addr_list', '')
    if addresses:
        os.environ['EPICS_CA_ADDR_LIST'] = addresses
    os.environ['EPICS_CA_AUTO_ADDR_LIST'] = 'YES' if config.get('epics_ca_auto_addr_list', False) else 'NO'
    os.environ.setdefault("EPICS_CA_MAX_ARRAY_BYTES", "262144")
    import aioca
    stop = asyncio.Event()
    failure = []
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: (stop.set(), wake.set()))
    wake = asyncio.Event()
    save_interval = SaveInterval(interval, wake)
    interval_ioc = start_interval_pv(config, save_interval, loop, output, pvs)
    recorder = CSVRecorder(output, pvs)
    monitors = []

    def callback(pv, value):
        try:
            recorder.update(pv, value)
        except Exception as exc:
            failure.append(exc)
            stop.set()
            wake.set()

    try:
        for pv in pvs:
            monitors.append(aioca.camonitor(pv, lambda value, pv=pv: callback(pv, value), notify_disconnect=True))
        print(f'Recording {len(pvs)} PVs every {interval:g} seconds to {recorder.path}', flush=True)
        deadline = loop.time() + interval
        while not stop.is_set():
            try:
                await asyncio.wait_for(wake.wait(), max(0, deadline - loop.time()))
                wake.clear()
                deadline = loop.time() + save_interval.seconds
            except asyncio.TimeoutError:
                if not stop.is_set():
                    recorder.snapshot()
                    deadline = max(deadline + save_interval.seconds, loop.time() + save_interval.seconds)
        if failure:
            raise failure[0]
    finally:
        for monitor in monitors:
            monitor.close()
        recorder.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings', type=Path, default=Path(__file__).parent/'settings/settings.yaml')
    parser.add_argument('--interval', type=float, help='Override save interval in seconds')
    parser.add_argument('--list-pvs', action='store_true', help='Show configuration without connecting to EPICS')
    args = parser.parse_args()
    config, interval, pvs, output = load_settings(args.settings)
    if args.interval is not None:
        interval = args.interval
    if not math.isfinite(interval) or interval <= 0:
        parser.error('Interval must be positive and finite')
    if args.list_pvs:
        print('\n'.join(pvs))
        print(f'{len(pvs)} PVs; interval={interval:g}s; output={output}')
        return
    asyncio.run(run(config, interval, pvs, output))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError) as exc:
        print(f'Archiver error: {exc}', file=sys.stderr)
        raise SystemExit(1)
