"""Schema9/own010 flex config and diagnostic layout; previous offsets frozen."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CAPTURE_FLOATS=('low_hz','high_hz','fault_hz','tolerance_hz','stale_ms','filter_ms')
ARRAYS=('ethanol_bins','fuel_pct','spark_deg','temperature_c','temperature_pct')
BOOLEANS=('enabled','temperature_enabled','input_confirmed')
OFFSET=7808;USED_END=7968;PAGE_BYTES=8192;LIVE_OFFSET=640;LIVE_BYTES=832
OFFSETS={name:OFFSET+4*n for n,name in enumerate(BOOLEANS)}
OFFSETS['cycles']=7820
OFFSETS.update({name:7824+4*n for n,name in enumerate(CAPTURE_FLOATS)})
OFFSETS.update({name:7848+24*n for n,name in enumerate(ARRAYS)})
UNITS=dict(low_hz='Hz',high_hz='Hz',fault_hz='Hz',tolerance_hz='Hz',stale_ms='ms',filter_ms='ms',cycles='cycles',ethanol_bins='% ethanol',fuel_pct='%',spark_deg='deg delta',temperature_c='C',temperature_pct='%')
LIMITS=dict(low_hz=(10,180),high_hz=(20,200),fault_hz=(25,500),tolerance_hz=(0,2),stale_ms=(250,2000),filter_ms=(0,5000),cycles=(2,32),ethanol_bins=(0,100),fuel_pct=(0,255),spark_deg=(-40,40),temperature_c=(-40,125),temperature_pct=(0,255))
LABELS=dict(enabled='Apply flex fuel and spark corrections',temperature_enabled='Apply fuel-temperature correction',input_confirmed='Protected GPIO38 wiring and reset behavior checked',low_hz='E0 frequency',high_hz='E100 frequency',fault_hz='Sensor fault threshold',tolerance_hz='Frequency tolerance',stale_ms='Completed sample expiry',filter_ms='Measurement filter time constant',cycles='Complete cycles per window',ethanol_bins='Ethanol bins',fuel_pct='Fuel correction',spark_deg='Spark addition',temperature_c='Fuel-temperature bins',temperature_pct='Fuel-temperature correction')
DEFAULT=dict(input_confirmed=False,capture=dict(low_hz=50,high_hz=150,fault_hz=170,tolerance_hz=1,stale_ms=250,filter_ms=0,cycles=8),correction=dict(enabled=False,temperature_enabled=False,ethanol_bins=[0,20,40,60,80,100],fuel_pct=[100]*6,spark_deg=[0]*6,temperature_c=[-40,0,20,40,80,125],temperature_pct=[100]*6))
def group(name):return None if name=='input_confirmed'else 'capture'if name in CAPTURE_FLOATS or name=='cycles'else 'correction'
def get(config,name):return config[name]if group(name)is None else config[group(name)][name]
def set_value(config,name,value):
 if group(name)is None:config[name]=value
 else:config[group(name)][name]=value
def cpp(name):return 't.flex_fuel.'+(group(name)+'.'if group(name)else '')+name
def constant(name):return 'flex_'+name
SOURCE_NAMES=('unavailable','target_capture','synthetic_edges','synthetic_value')
REASONS=('disabled','acquiring','ready','invalid_configuration','unavailable','repeated_level','time_reversed','edge_gap','short_edge_interval','frequency_out_of_range','sensor_fault_frequency','low_pulse_width_out_of_range','capture_overflow','stale','future_edge','source_changed','configuration_changed','capture_configuration_mismatch','protected_input_unconfirmed','malformed_capture_sample','raw_capture_required','synthetic_value_only','capture_clock_fault')
VALUES=('frequency_hz','low_pulse_us','ethanol_pct','fuel_temp_c','unfiltered_ethanol_pct','unfiltered_fuel_temp_c','sample_age_ms','fuel_pct','spark_add_deg','temperature_pct')
VALUE_UNITS=('Hz','us','% ethanol','C','% ethanol','C','ms','%','deg delta','%')
FLAGS=('required','configuration_match','value_qualified','raw_capture_qualified','control_ok','capture_valid','sample_value_valid','pending_fault','frequency_clamped','temperature_clamped','input_confirmed','corrections_enabled','corrections_valid','spark_bypassed','spark_clamped','zero_factor','available')
CODES=('source_code','reason_code','capture_reason_code','last_fault_code','correction_reason_code','window_cycles','configuration_revision')
TIMES=('sample_us','window_start_us','last_edge_us','raw_edges','fault_generation','acknowledged_generation','config_epoch')
def log_fields():
 labels=('FrequencyHz','LowPulseUs','EthanolPct','FuelTempC','UnfilteredEthanolPct','UnfilteredFuelTempC','SampleAgeMs','FuelPct','SparkAddDeg','TemperaturePct')
 return [('Flex'+label,unit,key)for label,unit,key in zip(labels,VALUE_UNITS,VALUES)]+[('Flex'+key.title().replace('_',''),'code',key)for key in CODES]+[('Flex'+key.title().replace('_',''),'us'if key.endswith('_us')else 'count',key)for key in TIMES]+[('Flex'+key.title().replace('_',''),'bool',key)for key in FLAGS]
