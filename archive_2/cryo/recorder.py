"""Cryo snapshots with optional magnet-fill-dependent sampling."""
from ..tools.runtime import record
from .sampling import Sampling

async def run(config, *, ready=lambda: None):
    sampling=Sampling(config['save_interval_s'],config.get('magnet_fill'))
    await record(config,ready=ready,sampling=sampling)
