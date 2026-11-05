"""Own007 transient field ABI; physical validation stays in the C++ core."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DEFAULT=json.loads((ROOT/'config/engine/defaults.json').read_text())['transient_enrichment']
MODES=('legacy_tps','off','tps_rate','map_rate')
MODE_LABELS=('Legacy TPS decay','Off','TPS rate table','MAP rate table')
APPLIES=('multiply','add_reference')
APPLY_LABELS=('Multiply fuel','Add reference fuel')
SCALARS=('sample_period_ms','tps_threshold_pct_s','map_threshold_kpa_s','tps_min_change_pct','map_min_change_kpa',
 'duration_ms','max_enrichment_pct','decel_fuel_pct','rpm_taper_start','rpm_taper_end','cold_multiplier_pct','cold_taper_start_c','cold_taper_end_c')
ARRAYS=('tps_rates','tps_added_pct','map_rates','map_added_pct')
OFFSET=4992
SCALAR_OFFSETS={name:OFFSET+8+i*4 for i,name in enumerate(SCALARS)}
ARRAY_OFFSETS={name:OFFSET+8+len(SCALARS)*4+i*16 for i,name in enumerate(ARRAYS)}
USED_END=OFFSET+8+len(SCALARS)*4+len(ARRAYS)*16
PAGE_BYTES=5120;LIVE_BYTES=320
assert len(SCALARS)==13 and USED_END==5116
assert set(DEFAULT)=={'mode','apply',*SCALARS,*ARRAYS}
UNITS={name:'%' for name in SCALARS+ARRAYS}
UNITS.update(sample_period_ms='ms',duration_ms='ms',tps_threshold_pct_s='%/s',map_threshold_kpa_s='kPa/s',tps_min_change_pct='%',map_min_change_kpa='kPa',rpm_taper_start='RPM',rpm_taper_end='RPM',cold_taper_start_c='C',cold_taper_end_c='C',tps_rates='%/s',map_rates='kPa/s')
LIMITS=dict(sample_period_ms=(5,100),tps_threshold_pct_s=(0,2550),map_threshold_kpa_s=(0,2550),tps_min_change_pct=(0,10),map_min_change_kpa=(0,10),duration_ms=(0,2000),max_enrichment_pct=(0,650),decel_fuel_pct=(0,100),rpm_taper_start=(50,8000),rpm_taper_end=(50,8000),cold_multiplier_pct=(100,255),cold_taper_start_c=(-40,140),cold_taper_end_c=(-40,140),tps_rates=(0,2550),tps_added_pct=(0,255),map_rates=(0,2550),map_added_pct=(0,255))
VALUE_NAMES=('tps_dot_pct_s','map_dot_kpa_s','window_ms','trigger_dot','correction_pct','unclamped_pct','remaining_ms','added_fuel_mg')
LIVE_NAMES=('aeTpsDot','aeMapDot','aeWindowMs','aeTriggerDot','aeCorrectionPct','aeUnclampedPct','aeRemainingAtSampleMs','aeAddedFuelMg')
LIVE_UNITS=('%/s','kPa/s','ms','source_units/s','%','%','ms','mg')
def name(field):return 'ae_'+field
