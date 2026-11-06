"""Schema8/own009 secondary-table metadata. Historical own008 offsets remain frozen."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DEFAULT=json.loads((ROOT/'config/engine/defaults.json').read_text())['secondary_tables']
KINDS=('fuel','spark')
ENUM_FIELDS=('mode','source','axis','cells','condition')
SCALARS=('threshold','debounce_ms')
ENUMS=dict(mode=('off','multiply','add','conditional','input'),source=('map','tps','imap_emap'),axis=('map_kpa','tps_pct','imap_emap_pct'),cells=('absolute','multiplier','adder'),condition=('rpm','map_kpa','tps_pct','ethanol_pct'))
LABELS=dict(mode=('Off','Multiply percent','Add','Conditional switch','Qualified input switch'),source=('MAP kPa','TPS percent','IMAP / EMAP percent'),axis=('MAP kPa','TPS percent','IMAP / EMAP percent'),cells=('Absolute table value','Multiplier percent','Additive table value'),condition=('RPM','MAP kPa','TPS percent','Qualified ethanol percent'))
AXIS_UNITS=dict(map_kpa='kPa',tps_pct='% TPS',imap_emap_pct='% IMAP/EMAP')
CONDITION_UNITS=dict(rpm='RPM',map_kpa='kPa',tps_pct='% TPS',ethanol_pct='% ethanol')
CELL_UNITS=dict(fuel=dict(absolute='% coefficient',multiplier='% multiplier',adder='percentage_points'),spark=dict(absolute='deg BTDC',multiplier='% multiplier',adder='deg delta'))
def constant_unit(kind,key,rule):
 return 'RPM' if key=='mapRpm' else AXIS_UNITS[rule['axis']] if key=='mapLoad' else CELL_UNITS[kind][rule['cells']] if key=='mapTable' else CONDITION_UNITS[rule['condition']] if key=='threshold' else 'ms' if key=='debounce_ms' else ''
CPP_ENUMS=dict(mode='Mode',source='load::Source',axis='load::Axis',cells='Cells',condition='Condition')
OFFSET=5376;RULE_BYTES=36;CONTROL_END=5448
MAP_OFFSETS=dict(fuel=5504,spark=6656);USED_END=7808
PAGE_BYTES=8192;LIVE_BYTES=640;LIVE_OFFSET=416;LIVE_STRIDE=80
VALUE_NAMES=('primary','primary_corrected','secondary','combined','coordinate','condition_value','input_age_ms','threshold','debounce_ms')
VALUE_LABELS=('Primary','PrimaryCorrected','Secondary','Combined','Coordinate','ConditionValue','InputAgeMs','Threshold','DebounceMs')
CODE_FIELDS=('mode','cells','source','reason','input_source','condition')
REASONS=('disabled','multiply','add','condition_primary','condition_secondary','input_primary','input_secondary','input_initial_qualification','input_unavailable','input_stale','input_time_reversed','required_map_unavailable','required_tps_unavailable','required_emap_unavailable','required_ethanol_unavailable','cranking_spark_bypass','invalid_configuration','invalid_arithmetic')
INPUT_SOURCES=('unavailable','target_protected_input','synthetic_input')
BOOLEAN_FIELDS=('available','evaluated','active','clamped','pending','input_qualified','input_level','pending_level','input_valid','input_raw','active_high','valid')
LOG_CODE_FIELDS=tuple(k+'_code' for k in CODE_FIELDS)+('axis_code','input_channel')
LOG_CODE_LABELS=('Mode','Cells','Source','Reason','InputSource','Condition','Axis','InputChannel')
def log_fields(kind):
 prefix='Sec'+kind.title();units=('%' if kind=='fuel' else 'deg',)*2+('cell_units','%' if kind=='fuel' else 'deg','source_units','condition_units','ms','condition_units','ms')
 return [(prefix+label,unit,key) for label,unit,key in zip(VALUE_LABELS,units,VALUE_NAMES)]+[(prefix+'Flags','bitfield','flags')]+[(prefix+label,'code',key) for label,key in zip(LOG_CODE_LABELS,LOG_CODE_FIELDS)]+[(prefix+'ObservedUs','us','input_observed_us')]+[(prefix+key.title().replace('_',''),'bool',key) for key in BOOLEAN_FIELDS]
def rule_offset(kind):return OFFSET+KINDS.index(kind)*RULE_BYTES
def enum_offset(kind,key):return rule_offset(kind)+4*ENUM_FIELDS.index(key)
def scalar_offset(kind,key):return rule_offset(kind)+20+4*SCALARS.index(key)
def name(kind,key):return 'secondary_'+kind+'_'+key
def live_prefix(kind):return 'Sec'+kind.title()
def limits(key,rule=None):
 if key=='debounce_ms':return (0,500)
 condition=(rule or {}).get('condition','rpm');return (0,10000 if condition=='rpm' else 110 if condition=='map_kpa' else 100)
