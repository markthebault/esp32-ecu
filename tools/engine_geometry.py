"""Declared even-fire research-engine geometry, independent of ECU calibration.

The ordinary host run assumes the entered cylinder count/order/displacement.
Tests can hold this object fixed while changing ECU calibration. Tooth and cam
locations are physical fixture assumptions, never copied from timing offsets.
"""
from dataclasses import dataclass
import math
from profile_config import LAYOUT, MAXIMUM

INJECTOR_CHANNELS=tuple(LAYOUT['injector_channels'])
COIL_CHANNELS=tuple(LAYOUT['coil_channels'])
CHANNEL_EXTENT=max(INJECTOR_CHANNELS+COIL_CHANNELS)+1


def channel_kind(channel):
    if type(channel) is not int:return None
    if channel in INJECTOR_CHANNELS:return 'injector',INJECTOR_CHANNELS.index(channel)
    if channel in COIL_CHANNELS:return 'coil',COIL_CHANNELS.index(channel)
    return None


@dataclass(frozen=True)
class EngineGeometry:
    cylinders:int=4
    firing_order:tuple=(1,3,4,2)
    displacement_cc:float=2000.
    tooth1_tdc_deg:float=90.
    cam_edge_deg:float=540.

    def __post_init__(self):
        if type(self.cylinders) is not int or not 1<=self.cylinders<=MAXIMUM:
            raise ValueError('Physical research profile requires1..8 cylinders')
        order=tuple(self.firing_order)
        if len(order)!=self.cylinders or any(type(c) is not int for c in order) or order[0]!=1 or sorted(order)!=list(range(1,self.cylinders+1)):
            raise ValueError('Physical firing order must start at1 and contain each cylinder once')
        object.__setattr__(self,'firing_order',order)
        for value,lo,hi in ((self.displacement_cc,25,12000),(self.tooth1_tdc_deg,0,360),(self.cam_edge_deg,0,720)):
            if type(value) not in (int,float) or not math.isfinite(value) or not lo<=value<=hi:
                raise ValueError('Invalid physical research geometry')

    @classmethod
    def from_tune(cls,tune):
        count=tune['engine']['cylinders']
        return cls(count,tuple(tune['timing']['firing_order'][:count]),tune['engine']['displacement_cc'])

    @property
    def displacement_m3(self):return self.displacement_cc*1e-6

    @property
    def compression_tdc_deg(self):
        return tuple((self.tooth1_tdc_deg+720*self.firing_order.index(c+1)/self.cylinders)%720 for c in range(self.cylinders))

    @property
    def injector_channels(self):return INJECTOR_CHANNELS[:self.cylinders]

    @property
    def coil_channels(self):return COIL_CHANNELS[:self.cylinders]

    def actuator(self,channel):
        entry=channel_kind(channel)
        if entry is None or entry[1]>=self.cylinders:
            raise ValueError('Actuator is outside the declared physical cylinder profile')
        return entry

    def summary(self):
        return dict(cylinders=self.cylinders,firing_order=list(self.firing_order),
                    displacement_cc=self.displacement_cc,compression_tdc_deg=list(self.compression_tdc_deg),
                    tooth1_tdc_deg=self.tooth1_tdc_deg,cam_edge_deg=self.cam_edge_deg,
                    injector_channels=list(self.injector_channels),coil_channels=list(self.coil_channels),
                    wheel_slots=60,missing_teeth=2,
                    scope='Declared even-fire four-stroke synthetic physical profile; uncalibrated')
