import csv
from datetime import datetime,timezone
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import xml.etree.ElementTree as E
import pytest
from conftest import ROOT


def test_settings_are_independent(module,tmp_path):
    cfg=module('tools.config')
    configs=[cfg.load(name,data_root=tmp_path) for name in cfg.SUBSYSTEMS]
    assert len({c['server_port'] for c in configs})==4
    assert len({c['control_prefix'] for c in configs})==4
    assert len({c['output'] for c in configs})==4
    assert all(c['save_interval_s']==1 for c in configs)
    assert configs[0]['magnet_fill']['enabled'] is False


def test_csv_scalar_missing_nonfinite(module,tmp_path):
    w=module('tools.writers').CSVWriter(tmp_path,'cryo',['A','B'])
    w.append({'A':2,'B':float('nan')});w.append({});w.close()
    with w.path.open() as f:rows=list(csv.reader(f))
    assert rows[0]==['timestamp_utc','A','B']
    assert rows[1][1:]==['2',''];assert rows[2][1:]==['','']
    assert 'cryo_' in w.path.name


def test_fill_sampling_future_option(module):
    Sampling=module('cryo.sampling').Sampling
    clock=[0.0]
    s=Sampling(5,dict(enabled=True,active_pv='TEST:FILL',interval_s=.5,settling_time_s=10),now=lambda:clock[0])
    assert s.effective==.5 # configured unknown-status fallback
    s.update(0);assert s.effective==5
    s.update(1);assert s.effective==.5
    clock[0]=1;s.update(0);assert s.effective==.5
    clock[0]=11;assert s.effective==5
    s.normal=.1;s.update(1);assert s.effective==.1 # fill never slows a faster normal rate
    s.update(None);assert s.effective==.1
    with pytest.raises(ValueError):Sampling(5,dict(enabled=True))


def test_burns_capture_immutable_parameters_and_embed_waveform(module,tmp_path):
    BurnLogger=module('ssrf.event_logger').BurnLogger
    params={'FM_PERIOD_S':.1,'FM_REPEATS':2,'VLOW_V':-1,'VHIGH_V':1}
    log=BurnLogger(tmp_path,sample_count=32)
    log.transition('IDLE',params)
    log.transition('RUNNING',params,session_id='S1')
    params['VHIGH_V']=99
    log.transition('RUNNING',params)
    log.transition('COMPLETE',params)
    log.transition('COMPLETE',params)
    log.transition('RUNNING',params)
    log.transition('ABORTED',params)
    log.close()
    rows=[json.loads(line) for line in log.writer.path.read_text().splitlines()]
    assert len(rows)==4
    assert rows[0]['burn_id']==rows[1]['burn_id']!=rows[2]['burn_id']
    assert rows[1]['parameters']['VHIGH_V']==1
    assert rows[1]['outcome']=='completed'
    assert rows[3]['outcome']=='aborted'
    assert len(rows[1]['waveform']['values'])==32
    assert rows[1]['waveform']['sample_interval_s']==pytest.approx(.2/31)
    assert 'placeholder' not in log.writer.path.read_text()
    history=module('tools.history')
    assert history.read_burn(tmp_path,0)['burn_id']==rows[2]['burn_id']
    assert history.read_burn(tmp_path,1)['burn_id']==rows[0]['burn_id']


def test_failure_and_interruption_are_not_success(module,tmp_path):
    def broken(*args):raise ValueError('bad reconstruction')
    b=module('ssrf.event_logger').BurnLogger(tmp_path,reconstruction=broken)
    b.transition('RUNNING',{});b.transition(None,{})
    b.close()
    rows=[json.loads(x) for x in b.writer.path.read_text().splitlines()]
    assert rows[-1]['outcome']=='interrupted'
    assert rows[-1]['waveform'] is None
    assert rows[-1]['waveform_error']=='bad reconstruction'


def test_recipe_event_api_preserved(module,tmp_path):
    logger=module('ssrf.event_logger').JsonlEventLogger(directory=tmp_path)
    event=logger.append(event_type='recipe_requested',source='test',session_id='session',data={'p':2})
    rows=module('ssrf.event_logger').read_jsonl(next(tmp_path.glob('*.jsonl')))
    assert rows[0]['event_id']==event.event_id
    assert rows[0]['data']=={'p':2}


def test_history_csv_and_empty_window(module,tmp_path):
    path=tmp_path/'cryo_20260101.csv'
    path.write_text('timestamp_utc,A\n2026-01-01T01:00:00Z,1\n2026-01-01T01:30:00Z,\n')
    h=module('tools.history');now=datetime(2026,1,1,2,tzinfo=timezone.utc)
    x,y,n,_,_=h.read_csv(tmp_path,'cryo','A',1,0,now)
    assert x==[-1,-.5] and n==2 and math.isnan(y[1])
    assert h.read_csv(tmp_path,'cryo','B',1,0,now)[2]==0


def test_ownership_lock(module,tmp_path):
    Lease=module('tools.lifecycle').Lease
    a=Lease(tmp_path)
    try:
        with pytest.raises(RuntimeError):Lease(tmp_path)
        a.ready();assert module('tools.lifecycle').active(tmp_path)
    finally:a.close()
    assert module('tools.lifecycle').active(tmp_path) is None


def test_package_can_be_renamed(tmp_path):
    target=tmp_path/'a_completely_different_name'
    shutil.copytree(ROOT,target,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache'))
    for name in ('cryo','microwave','magnet','ssrf'):
        result=subprocess.run([sys.executable,str(target/'run.py'),name,'list','--data-root',str(tmp_path/'data')],cwd=tmp_path,capture_output=True,text=True)
        assert result.returncode==0,result.stderr
        assert str(tmp_path/'data'/name) in result.stdout


def test_gui_references_existing_files_and_only_controls(module):
    for p in (ROOT/'gui').glob('*.bob'):
        tree=E.parse(p)
        for a in tree.findall('.//action[@type="open_display"]'):
            assert (p.parent/a.findtext('file')).exists()
        for a in tree.findall('.//action[@type="write_pv"]'):
            assert a.findtext('pv_name').startswith('ca://$(P):')
    assert len(list((ROOT/'gui').glob('*_channels.bob')))==4
