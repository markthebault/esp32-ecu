"""Own008 load/pressure/AFR ABI metadata; native core validates physical use."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DEFAULT=json.loads((ROOT/'config/engine/defaults.json').read_text())['load_model']
SOURCES=('map','tps','imap_emap','follow_fuel')
SOURCE_LABELS=('MAP kPa','TPS percent','IMAP / EMAP percent','Follow primary fuel')
AXES=('map_kpa','tps_pct','imap_emap_pct')
AXIS_LABELS=('MAP kPa','TPS percent','IMAP / EMAP percent')
PRESSURES=('none','map_100kpa','map_baro')
PRESSURE_LABELS=('Off: 100 kPa reference','MAP / 100 kPa','MAP / baro')
AUX_ROLES=('postcat_monitor','emap','baro')
AUX_LABELS=('J16 postcat monitor','J16 exhaust absolute pressure','J16 barometric absolute pressure')
BARO_SOURCES=('fixed','aux');BARO_LABELS=('Fixed manual kPa','Live calibrated J16')
AFR_MODES=('off','target','measured');AFR_LABELS=('Off:stoichiometric basis','Incorporate target lambda','Measured / target lambda')
ENUM_FIELDS=('fuel_source','spark_source','lambda_source','trim_source','pressure','aux_role','baro_source','ve_axis','spark_axis','lambda_axis','trim_axis','afr')
SCALARS=('fixed_baro_kpa','afr_delay_s')
ENUMS={**{k:SOURCES[:3] if k in ENUM_FIELDS[:2] else SOURCES for k in ENUM_FIELDS[:4]},'pressure':PRESSURES,'aux_role':AUX_ROLES,'baro_source':BARO_SOURCES,**{k:AXES for k in ENUM_FIELDS[7:11]},'afr':AFR_MODES}
LABELS={**{k:SOURCE_LABELS[:3] if k in ENUM_FIELDS[:2] else SOURCE_LABELS for k in ENUM_FIELDS[:4]},'pressure':PRESSURE_LABELS,'aux_role':AUX_LABELS,'baro_source':BARO_LABELS,**{k:AXIS_LABELS for k in ENUM_FIELDS[7:11]},'afr':AFR_LABELS}
CPP_ENUMS={**{k:'Source' for k in ENUM_FIELDS[:4]},'pressure':'Pressure','aux_role':'AuxRole','baro_source':'BaroSource',**{k:'Axis' for k in ENUM_FIELDS[7:11]},'afr':'Afr'}
OFFSET=5120;ENUM_OFFSETS={k:OFFSET+4*n for n,k in enumerate(ENUM_FIELDS)}
SCALAR_OFFSETS={k:OFFSET+4*len(ENUM_FIELDS)+4*n for n,k in enumerate(SCALARS)}
USED_END=OFFSET+4*(len(ENUM_FIELDS)+len(SCALARS));PAGE_BYTES=5376;LIVE_BYTES=416
assert USED_END==5176 and set(DEFAULT)==set(ENUM_FIELDS+SCALARS)
VALUE_NAMES=('fuel_load','spark_load','lambda_load','trim_load','pressure_factor','baro_kpa','emap_kpa','aux_kpa','afr_factor')
LIVE_NAMES=('loadFuel','loadSpark','loadLambda','loadTrim','loadPressureFactor','loadBaro','loadEmap','loadAux','loadAfrFactor')
LIVE_UNITS=('source_units','source_units','source_units','source_units','ratio','kPa','kPa','kPa','ratio')
LIMITS=dict(fixed_baro_kpa=(50,110),afr_delay_s=(0,120));UNITS=dict(fixed_baro_kpa='kPa',afr_delay_s='s')
AFR_STATES=('off','target_incorporation','running_delay','cranking_neutral','wideband_unavailable','measured_ratio','invalid_target','running_clock_unavailable')
def name(field):return 'load_'+field
