"""Periodic ssRF snapshots plus execution-triggered embedded-waveform burn log."""
from ..tools.runtime import record
from .event_logger import BurnLogger

async def run(config, *, ready=lambda: None):
    await record(config,ready=ready,burn_factory=BurnLogger)
