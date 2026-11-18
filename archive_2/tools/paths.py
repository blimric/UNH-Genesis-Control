"""Shared recording paths independent of the source directory's name."""
import os
from pathlib import Path
from .config import load


def ssrf_event_dir():return load('ssrf')['output']/'events'


def resolve_recording_path(path,default):
    if path is None or not str(path).strip():return Path(default)
    requested=Path(path).expanduser()
    return requested if requested.is_absolute() else Path(os.environ.get('GENESIS_DATA_ROOT') or load('ssrf')['data_root'])/requested
