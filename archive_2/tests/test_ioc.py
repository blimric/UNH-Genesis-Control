"""End-to-end tests only use private loopback IOCs and temporary outputs."""
import csv
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import yaml
from conftest import ROOT


def free_port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]


def test_independent_recorders_burns_fill_history_and_stop(tmp_path):
    renamed=tmp_path/'archive'
    shutil.copytree(ROOT,renamed,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache'))
    runner=renamed/'run.py'
    input_port=free_port();ports=[free_port() for _ in range(4)]
    assert len(set([input_port,*ports]))==5
    env=os.environ.copy();env['EPICS_CAS_INTF_ADDR_LIST']='127.0.0.1'
    # A local-only fake instrument. Nothing uses the actual lab PVs or addresses.
    source=tmp_path/'source.py'
    source.write_text('''
import os,sys
os.environ['EPICS_CAS_SERVER_PORT']=sys.argv[1]
from softioc import builder,softioc,asyncio_dispatcher
builder.aOut('TEST:VALUE',initial_value=2.5)
builder.boolOut('TEST:FILL',initial_value=False)
builder.stringOut('TEST:STATE',initial_value='IDLE')
builder.stringOut('TEST:SESSION',initial_value='SESSION1')
builder.aOut('TEST:PERIOD',initial_value=.1)
builder.aOut('TEST:REPEATS',initial_value=2)
builder.aOut('TEST:HIGH',initial_value=1)
builder.aOut('TEST:LOW',initial_value=-1)
builder.LoadDatabase()
softioc.iocInit(asyncio_dispatcher.AsyncioDispatcher(),enable_pva=False)
import time
while True:time.sleep(1)
''')
    logfiles=[];processes=[]
    def launch(args,name):
        f=(tmp_path/(name+'.log')).open('w');logfiles.append(f)
        proc=subprocess.Popen(args,env=env,stdout=f,stderr=subprocess.STDOUT)
        processes.append(proc);return proc
    launch([sys.executable,str(source),str(input_port)],'source')
    shared=tmp_path/'shared';configs={}
    names=('cryo','microwave','magnet','ssrf')
    try:
        for i,name in enumerate(names):
            directory=tmp_path/name;directory.mkdir()
            (directory/'pvs.yaml').write_text('pvs: ["TEST:VALUE"]\n')
            cfg={'subsystem':name,'save_interval_s':.2+i*.05,'control_prefix':'TEST:'+name.upper(),
                 'server_port':ports[i],'data_root':str(shared),'pv_file':'pvs.yaml',
                 'epics_ca_addr_list':f'127.0.0.1:{input_port}'}
            if name=='cryo':cfg['magnet_fill']={'enabled':True,'active_pv':'TEST:FILL','active_value':1,'interval_s':.02,'settling_time_s':0,'unavailable_policy':'normal'}
            if name=='ssrf':cfg['burn_logging']={'enabled':True,'state_pv':'TEST:STATE','session_pv':'TEST:SESSION','sample_count':32,'parameters':{'FM_PERIOD_S':'TEST:PERIOD','FM_REPEATS':'TEST:REPEATS','VHIGH_V':'TEST:HIGH','VLOW_V':'TEST:LOW'}}
            path=directory/'settings.yaml';path.write_text(yaml.safe_dump(cfg));configs[name]=path
            launch([sys.executable,str(runner),name,'run','--settings',str(path)],name)
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            if all((shared/n/'.runtime/recorder.json').exists() for n in names):break
            if any(p.poll() is not None for p in processes):break
            time.sleep(.1)
        assert all((shared/n/'.runtime/recorder.json').exists() for n in names), '\n'.join(p.read_text() for p in tmp_path.glob('*.log'))
        addresses=' '.join(f'127.0.0.1:{p}' for p in [input_port,*ports])
        client_env=env.copy();client_env.update(EPICS_CA_ADDR_LIST=addresses,EPICS_CA_AUTO_ADDR_LIST='NO',EPICS_CA_MAX_ARRAY_BYTES='1048576')
        client='''
import asyncio
from aioca import caget,caput
async def main():
    for _ in range(30):
        try:
            assert float(await caget('TEST:VALUE',timeout=1))==2.5
            break
        except Exception:await asyncio.sleep(.1)
    else:raise RuntimeError('Input IOC unreachable')
    await asyncio.sleep(.5)
    await caput('TEST:MICROWAVE:SaveInterval',.03,wait=True)
    assert abs(float(await caget('TEST:MAGNET:SaveInterval'))-.3)<.001
    await caput('TEST:FILL',1,wait=True)
    await asyncio.sleep(.15)
    assert abs(float(await caget('TEST:CRYO:EffectiveInterval'))-.02)<.001
    await caput('TEST:STATE','RUNNING',wait=True)
    await asyncio.sleep(.15)
    await caput('TEST:HIGH',99,wait=True)
    await caput('TEST:STATE','COMPLETE',wait=True)
    await asyncio.sleep(.2)
    await caput('TEST:SSRF:BurnLoad',1,wait=True)
    for _ in range(50):
        if str(await caget('TEST:SSRF:BurnStatus'))=='completed':break
        await asyncio.sleep(.05)
    else:raise RuntimeError(str(await caget('TEST:SSRF:BurnStatus')))
    assert len(await caget('TEST:SSRF:BurnY'))==32
    await caput('TEST:CRYO:HistoryLoad',1,wait=True)
    for _ in range(50):
        if 'rows' in str(await caget('TEST:CRYO:HistoryStatus')):break
        await asyncio.sleep(.05)
    else:raise RuntimeError('History failed')
    await caput('TEST:FILL',0,wait=True)
    await asyncio.sleep(.2)
    assert abs(float(await caget('TEST:CRYO:EffectiveInterval'))-.2)<.001
asyncio.run(main())
'''
        result=subprocess.run([sys.executable,'-c',client],env=client_env,capture_output=True,text=True,timeout=30)
        assert result.returncode==0,result.stderr+'\n'+'\n'.join(p.read_text() for p in tmp_path.glob('*.log'))
        for name in names:
            result=subprocess.run([sys.executable,str(runner),name,'stop','--settings',str(configs[name])],env=env,capture_output=True,text=True,timeout=20)
            assert result.returncode==0,result.stderr+result.stdout
        for name in names:
            assert not (shared/name/'.runtime/recorder.json').exists()
            path=next((shared/name).glob(name+'_*.csv'))
            with path.open() as f:rows=list(csv.reader(f))
            assert len(rows)>1 and any(row[1]=='2.5' for row in rows[1:])
        paths=list((shared/'ssrf/burns').glob('ssrf_burns_*.jsonl'));assert len(paths)==1
        burns=[json.loads(x) for x in paths[0].read_text().splitlines()]
        assert len(burns)==2 and burns[-1]['outcome']=='completed'
        assert burns[-1]['parameters']['VHIGH_V']==1
        assert len(burns[-1]['waveform']['values'])==32
        assert not list((shared/'ssrf').rglob('*.npz'))
    finally:
        for p in processes:
            if p.poll() is None:p.terminate()
        for p in processes:
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:p.kill();p.wait(timeout=5)
        for f in logfiles:f.close()
