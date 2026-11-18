from pathlib import Path
import math
import os
import yaml

ROOT = Path(__file__).resolve().parents[1]
SUBSYSTEMS = ('cryo', 'microwave', 'magnet', 'ssrf')


def positive(value, name):
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f'{name} must be positive and finite')
    return value


def load(subsystem, settings=None, data_root=None):
    if subsystem not in SUBSYSTEMS:
        raise ValueError('Unknown subsystem')
    path = Path(settings).resolve() if settings else ROOT/subsystem/'settings.yaml'
    cfg = yaml.safe_load(path.read_text())
    if cfg['subsystem'] != subsystem:
        raise ValueError('Settings subsystem does not match command')
    cfg['save_interval_s'] = positive(cfg['save_interval_s'], 'save_interval_s')
    cfg['server_port'] = int(cfg['server_port'])
    if not 1024 <= cfg['server_port'] <= 65535:
        raise ValueError('server_port must be between 1024 and 65535')
    pvs = yaml.safe_load((path.parent/cfg['pv_file']).read_text())['pvs']
    if not pvs or len(pvs) != len(set(pvs)) or any(not isinstance(p,str) or not p.strip() or p!=p.strip() for p in pvs):
        raise ValueError('PV list must contain distinct nonempty PV names')
    count=int(cfg.get('burn_logging',{}).get('sample_count',8192))
    if not 2<=count<=100000:raise ValueError('sample_count must be between 2 and 100000')
    cfg['pvs'] = pvs
    cfg['settings_path'] = str(path)
    # CLI overrides environment; environment overrides settings.
    directory = Path(data_root or os.environ.get('GENESIS_DATA_ROOT') or cfg['data_root']).expanduser()
    if not directory.is_absolute():directory = path.parent/directory
    cfg['data_root'] = str(directory.resolve())
    cfg['output'] = directory.resolve()/subsystem
    return cfg
