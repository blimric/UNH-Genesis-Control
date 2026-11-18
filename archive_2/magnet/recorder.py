"""Subsystem entry point; shared infrastructure owns file and EPICS mechanics."""
from ..tools.runtime import record

async def run(config, *, ready=lambda: None):
    await record(config, ready=ready)
