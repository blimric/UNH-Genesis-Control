from .config import positive


class FixedSampling:
    enabled=False
    def __init__(self,interval):self.normal=positive(interval,'save interval')
    @property
    def effective(self):return self.normal
