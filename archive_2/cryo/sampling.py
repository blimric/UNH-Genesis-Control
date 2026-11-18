"""Optional fill-dependent sampling; disabled until a real fill PV is supplied."""
import time
import math
from ..tools.config import positive


class Sampling:
    def __init__(self,normal,settings=None,now=time.monotonic):
        self.normal=positive(normal,'normal interval');self.cfg=settings or {};self.now=now
        self.fill=False;self.known=False;self.last_active=None
        self.enabled=bool(self.cfg.get('enabled',False))
        if self.enabled and not self.cfg.get('active_pv'):
            raise ValueError('Fill sampling requires active_pv')
        self.fast=positive(self.cfg.get('interval_s',self.normal),'fill interval')
        self.settle=float(self.cfg.get('settling_time_s',0))
        if not math.isfinite(self.settle) or self.settle < 0:raise ValueError('settling_time_s cannot be negative')
        self.policy=self.cfg.get('unavailable_policy','fast')
        if self.policy not in ('fast','normal'):raise ValueError('Invalid fill unavailable_policy')

    def update(self,value):
        self.known=value is not None
        self.fill=self.known and value==self.cfg.get('active_value',1)
        if self.fill:self.last_active=self.now()

    @property
    def effective(self):
        if not self.enabled:return self.normal
        active=self.fill or (not self.known and self.policy=='fast')
        settling=self.last_active is not None and self.now()-self.last_active<self.settle
        return min(self.normal,self.fast) if active or settling else self.normal
