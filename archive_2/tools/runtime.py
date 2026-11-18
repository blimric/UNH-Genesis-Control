"""Read-only EPICS collection with independent periodic and event recording."""
import asyncio
import math
import os
import signal
from .writers import CSVWriter,scalar
from .lifecycle import Lease
from .history import History
from .sampling import FixedSampling


async def record(config,*,ready=lambda:None,sampling=None,burn_factory=None):
    os.environ['EPICS_CA_ADDR_LIST']=config['epics_ca_addr_list']
    os.environ['EPICS_CA_AUTO_ADDR_LIST']='NO'
    os.environ['EPICS_CAS_SERVER_PORT']=str(config['server_port'])
    os.environ.setdefault('EPICS_CA_MAX_ARRAY_BYTES','1048576')
    from softioc import builder,softioc,asyncio_dispatcher
    import aioca
    loop=asyncio.get_running_loop();wake=asyncio.Event();stop=asyncio.Event();failure=[]
    sampling=sampling or FixedSampling(config['save_interval_s'])
    latest=dict.fromkeys(config['pvs']);monitors=[];queue=asyncio.Queue(maxsize=10000)
    burn_cfg=config.get('burn_logging',{});burn=None;worker=None
    prefix=config['control_prefix']
    def changed(value):
        sampling.normal=float(value);wake.set()
    interval=builder.aOut(prefix+':SaveInterval',initial_value=sampling.normal,EGU='s',PREC=3,
                          validate=lambda r,v:math.isfinite(v) and v>0,on_update=changed,always_update=True)
    effective=builder.aIn(prefix+':EffectiveInterval',initial_value=sampling.effective,EGU='s',PREC=3)
    history=History(builder,config)
    # Keep record/dispatcher/history references alive for the entire run.
    dispatcher=asyncio_dispatcher.AsyncioDispatcher(loop=loop)
    lease=Lease(config['output']);writer=None
    try:
        writer=CSVWriter(config['output'],config['subsystem'],config['pvs'])
        if burn_factory and burn_cfg.get('enabled',False):
            burn=burn_factory(config['output']/'burns',int(burn_cfg.get('sample_count',8192)))
        builder.LoadDatabase();softioc.iocInit(dispatcher,enable_pva=False)
        def fail(exc):
            failure.append(exc);stop.set();wake.set()
        def callback(pv,raw):
            try:
                value=scalar(raw) if raw is not None and getattr(raw,'ok',True) else None
                latest[pv]=value
                if sampling.enabled and pv==sampling.cfg['active_pv']:
                    before=sampling.effective
                    sampling.update(value)
                    if sampling.effective!=before:wake.set()
                if burn and pv==burn_cfg['state_pv']:
                    parameters={key:latest.get(name) for key,name in burn_cfg['parameters'].items()}
                    reason=latest.get('UNH:GEN:SSRF:SEQ:EXECUTION_REASON') or ''
                    queue.put_nowait((value,parameters,latest.get(burn_cfg.get('session_pv')),reason))
            except Exception as exc:fail(exc)
        async def events():
            try:
                while True:
                    item=await queue.get()
                    try:burn.transition(*item)
                    finally:queue.task_done()
            except asyncio.CancelledError:raise
            except Exception as exc:fail(exc)
        names=set(config['pvs'])
        # Subscribe to parameter sources first. RUNNING events capture the latest
        # monitor values; direct sequencer hooks can supply an atomic snapshot.
        if burn:
            names.update(burn_cfg['parameters'].values());names.add(burn_cfg['state_pv'])
            if burn_cfg.get('session_pv'):names.add(burn_cfg['session_pv'])
            names.add('UNH:GEN:SSRF:SEQ:EXECUTION_REASON')
            worker=asyncio.create_task(events())
        if sampling.enabled:names.add(sampling.cfg['active_pv'])
        ordered=sorted(names,key=lambda pv:pv==burn_cfg.get('state_pv'))
        for pv in ordered:
            monitors.append(aioca.camonitor(pv,lambda raw,pv=pv:callback(pv,raw),notify_disconnect=True))
        def stopping():stop.set();wake.set()
        for sig in (signal.SIGINT,signal.SIGTERM):loop.add_signal_handler(sig,stopping)
        lease.ready();ready()
        print(f"Recording {config['subsystem']} -> {writer.path}",flush=True)
        deadline=loop.time()+sampling.effective
        while not stop.is_set():
            effective.set(sampling.effective)
            try:
                # Revisit fill settling without busy-polling or postponing saves.
                await asyncio.wait_for(wake.wait(),min(1.0,max(0,deadline-loop.time())))
                wake.clear();deadline=loop.time()+sampling.effective
            except asyncio.TimeoutError:
                if loop.time()>=deadline and not stop.is_set():
                    writer.append(latest);deadline=loop.time()+sampling.effective
        if failure:raise failure[0]
    finally:
        try:
            for monitor in monitors:monitor.close()
            if worker:
                if not worker.done():
                    try:await asyncio.wait_for(queue.join(),5)
                    finally:
                        worker.cancel()
                        try:await worker
                        except asyncio.CancelledError:pass
                elif not worker.cancelled():worker.result()
        finally:
            try:
                if burn:burn.close()
            finally:
                try:
                    if writer:writer.close()
                finally:lease.close()
