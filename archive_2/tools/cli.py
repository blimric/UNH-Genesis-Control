import argparse
import asyncio
import importlib
import os
import signal
import subprocess
import sys
import time
from .config import ROOT,SUBSYSTEMS,load
from .lifecycle import active,identity


def execute(subsystem,command,settings=None,data_root=None):
    cfg=load(subsystem,settings,data_root);state=active(cfg['output'])
    if command=='list':
        print('\n'.join(cfg['pvs']));print(f"{len(cfg['pvs'])} PVs -> {cfg['output']}");return 0
    if command=='status':
        print(f"{subsystem}: UP PID {state['pid']}" if state else f'{subsystem}: DOWN');return 0 if state else 1
    if command=='stop':
        if not state:print(f'{subsystem}: DOWN');return 0
        if identity(state['pid'])!=state['identity']:raise RuntimeError('Recorder identity changed')
        os.kill(state['pid'],signal.SIGTERM)
        for _ in range(150):
            if not active(cfg['output']):print(f'{subsystem}: stopped');return 0
            time.sleep(.1)
        raise RuntimeError('Stop not complete; inspect recorder log')
    if command=='start':
        if state:print(f"{subsystem}: already UP PID {state['pid']}");return 0
        cfg['output'].mkdir(parents=True,exist_ok=True)
        log_path=cfg['output']/'recorder.log'
        cmd=[sys.executable,'-u',str(ROOT/'run.py'),subsystem,'run','--settings',cfg['settings_path'],'--data-root',cfg['data_root']]
        with log_path.open('a') as log:
            proc=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
        for _ in range(150):
            if proc.poll() is not None:raise RuntimeError(f'Recorder exited: inspect {log_path}')
            if active(cfg['output']):print(f'{subsystem}: UP PID {proc.pid}');return 0
            time.sleep(.1)
        raise RuntimeError(f'Start not confirmed; inspect {log_path}')
    package=__package__.rsplit('.',1)[0]
    module=importlib.import_module(f'{package}.{subsystem}.recorder')
    asyncio.run(module.run(cfg));return 0


def main(argv=None):
    parser=argparse.ArgumentParser(description='Independent Genesis recording; no hardware control')
    parser.add_argument('subsystem',choices=(*SUBSYSTEMS,'all'))
    parser.add_argument('command',choices=('run','start','status','stop','list'),nargs='?',default='run')
    parser.add_argument('--settings')
    parser.add_argument('--data-root',help='Override shared data root, also supports GENESIS_DATA_ROOT')
    args=parser.parse_args(argv)
    if args.subsystem=='all' and (args.command=='run' or args.settings):parser.error('all supports managed commands and default subsystem settings only')
    failed=0
    for name in SUBSYSTEMS if args.subsystem=='all' else (args.subsystem,):
        try:failed=max(failed,execute(name,args.command,args.settings,args.data_root))
        except Exception as exc:print(f'{name}: {exc}',file=sys.stderr);failed=1
    return failed
