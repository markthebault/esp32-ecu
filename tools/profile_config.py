"""Current profile/calibration extension. Legacy prefixes retain their offsets."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LAYOUT=json.loads((ROOT/'config/engine-profile.json').read_text())
SIGNATURE=LAYOUT['signature'].encode()
STRATEGIES=tuple(LAYOUT['strategies'])
PAGE=LAYOUT['page'];LIVE=LAYOUT['runtime'];MAXIMUM=LAYOUT['maximum_cylinders']
MSQ_MAXIMUM=LAYOUT['msq_maximum_bytes']
assert MAXIMUM==8 and PAGE['extra_order_offset']+4==PAGE['extra_fuel_offset']
assert PAGE['extra_fuel_offset']+4*PAGE['fuel_stride']==PAGE['extra_spark_offset']
assert PAGE['extra_spark_offset']+16==PAGE['used_end']<=12288
assert LIVE['extra_cylinders']+4*16==LIVE['used_end']<=1152

def order_offset(index):return 288+index if index<4 else PAGE['extra_order_offset']+index-4
def fuel_offset(index):return 3968+192*index if index<4 else PAGE['extra_fuel_offset']+PAGE['fuel_stride']*(index-4)
def spark_offset(index):return 4736+4*index if index<4 else PAGE['extra_spark_offset']+4*(index-4)
def live_offset(index):return 100+16*index if index<4 else LIVE['extra_cylinders']+16*(index-4)
