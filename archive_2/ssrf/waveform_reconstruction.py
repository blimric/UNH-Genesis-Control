"""Replace reconstruct() with the real waveform model when available.

This sine implementation is only a development stand-in and never controls RF.
"""
import math
from ..tools.config import positive


def reconstruct(parameters,sample_count=8192):
    if not 2<=int(sample_count)<=1000000:raise ValueError('sample_count out of range')
    period=positive(parameters.get('FM_PERIOD_S') or 1.0,'FM_PERIOD_S')
    repeats=int(parameters.get('FM_REPEATS') or 1)
    if repeats<1:raise ValueError('FM_REPEATS must be positive')
    high=parameters.get('VHIGH_V');low=parameters.get('VLOW_V')
    high=1.0 if high is None else float(high);low=-1.0 if low is None else float(low)
    if not math.isfinite(high) or not math.isfinite(low):raise ValueError('Nonfinite waveform bounds')
    duration=period*repeats;count=int(sample_count)
    return {'sample_interval_s':duration/(count-1),'units':'V',
            'values':[(high+low)/2+(high-low)/2*math.sin(2*math.pi*repeats*i/(count-1)) for i in range(count)]}
