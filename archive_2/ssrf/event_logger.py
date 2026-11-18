"""Burn boundaries and embedded waveform products; no EPICS writes or RF control."""
import copy
from dataclasses import dataclass,asdict
from pathlib import Path
import uuid
from ..tools.writers import JSONLWriter,utc_now
from .waveform_reconstruction import reconstruct

TERMINAL={'COMPLETE':'completed','FAILED':'failed','CLEANUP_FAILED':'cleanup_failed','ABORTED':'aborted'}


class BurnLogger:
    def __init__(self,directory,sample_count=8192,reconstruction=reconstruct):
        self.writer=JSONLWriter(directory,'ssrf_burns')
        self.sample_count=sample_count;self.reconstruction=reconstruction
        self.active=None;self.last_state=None

    def start(self,parameters,session_id=None):
        if self.active is not None:return self.active['burn_id']
        captured=copy.deepcopy(parameters)
        # Always persist the attempted burn even if reconstruction fails.
        waveform=None;error=None
        try:waveform=self.reconstruction(captured,self.sample_count)
        except Exception as exc:error=str(exc)
        self.active={'burn_id':uuid.uuid4().hex,'session_id':session_id,
                     'started_utc':utc_now(),'parameters':captured,'waveform':waveform}
        if error:self.active['waveform_error']=error
        self.writer.append({**self.active,'event':'burn_started','outcome':'in_progress'})
        return self.active['burn_id']

    def finish(self,outcome,reason=''):
        if self.active is None:return
        record={**self.active,'event':'burn_finished','ended_utc':utc_now(),'outcome':outcome,'reason':reason}
        self.writer.append(record)
        self.active=None

    def transition(self,state,parameters,session_id=None,reason=''):
        if state==self.last_state:return
        self.last_state=state
        if state=='RUNNING':self.start(parameters,session_id)
        elif state in TERMINAL:self.finish(TERMINAL[state],reason)
        elif state is None:self.finish('interrupted','Sequencer connection lost')

    def close(self):
        try:self.finish('interrupted','Recorder stopped before terminal event')
        finally:self.writer.close()


# Preserve the existing recipe/fitter event API in this folder too.
from .recipe_events import EventRecord, JsonlEventLogger, read_jsonl
