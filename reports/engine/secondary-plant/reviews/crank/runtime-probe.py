import ctypes,importlib.util,json,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent
PHASE=sys.argv[1]
SRC=OUT/(PHASE+'-sources')
def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def api(lib,signatures):
 result=ctypes.CDLL(str(lib))
 for name,(args,ret)in signatures.items():f=getattr(result,name);f.argtypes=args;f.restype=ret
 return result
P=ctypes.c_void_p;S=ctypes.c_char_p;U=ctypes.c_uint;T=ctypes.c_uint64;I=ctypes.c_int
obj=OUT/(PHASE+'-pic-cJSON.o');subprocess.run(['cc','-O2','-fPIC','-c',str(SRC/'external/cJSON/cJSON.c'),'-o',str(obj)],check=True)
commands=[]
for name,filename in [('engine','engine_bridge.cpp'),('observability','engine_observability_bridge.cpp')]:
 cmd=['c++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC','-I'+str(SRC/'external/cJSON'),'-I'+str(SRC/'firmware/main'),'-I'+str(SRC/'firmware/include'),str(SRC/'tools'/filename),str(obj),'-o',str(OUT/(PHASE+'-lib'+name+'.so'))]
 if name=='observability':cmd.append('-lcrypto')
 subprocess.run(cmd,check=True);commands.append(cmd)
engine=api(OUT/(PHASE+'-libengine.so'),{'engine_create':([],P),'engine_destroy':([P],None),'engine_canonicalize':([S],S),'engine_configure':([P,S],I),'engine_step':([P,S,T,T],S),'engine_data_json':([P],S)})
logger=api(OUT/(PHASE+'-libobservability.so'),{'data_create':([],P),'data_destroy':([P],None),'data_validate':([S],I),'data_log_command':([P,S,U,T,U],I),'data_log_append':([P,S,T],I),'data_log_header':([P],S),'data_log_page':([P,U,U],S),'data_log_msl':([P,U,S],S)})
er=module('bound_engine_runtime',SRC/'tools/engine_runtime.py');eo=module('bound_engine_observability',SRC/'tools/engine_observability.py')
tune=json.loads((SRC/'config/engine/defaults.json').read_text());tune['transient_enrichment']['mode']='off';tune['settings'].update(ego_enabled=False,dfco_enabled=False,afterstart_pct=0)
r=tune['secondary_tables']['spark'];r.update(mode='input',cells='absolute',debounce_ms=20,input_channel=1);r['map']['cells']=[14]*256
runtime=er.EngineRuntime(tune,bridge=engine);(OUT/(PHASE+'-runtime-tune.json')).write_text(json.dumps(runtime.tune,indent=2)+'\n');records=[];summary=[]
try:
 for now in range(1000000,1120001,20000):
  crank=now<1040000 or now==1080000;future=now==1060000;valid=now!=1080000
  inputs=dict(rpm=220 if crank else 550,synced=True,table_switches=[dict(valid=False,level=False,observed_us=str(now)),dict(valid=valid,level=True,observed_us=str(now+1 if future else now))])
  runtime.step(inputs,now,use_decoder=False);record=runtime.data();records.append(record);o=record['secondary_tables']['spark'];summary.append(dict(now=now,crank=crank,faults=record['controller_faults'],reason=o['reason'],active=o['active'],qualified=o['input_qualified']))
finally:runtime.close()
recorder=eo.EngineRecorder(bridge=logger)
try:
 assert recorder.command(dict(action='start',period_ms=20,duration_s=2),1000000)==200
 for record,now in zip(records,range(1000000,1120001,20000)):
  assert logger.data_validate(eo.encoded(record))==1
  assert recorder.append(record,now)
 assert recorder.command(dict(action='stop',log_id=1),1120001)==200
 header=recorder.header();header['boot_id']='0'*32;page=recorder.page(1,0);page['boot_id']=header['boot_id'];msl=recorder.msl(1,header['boot_id'])
finally:recorder.close()
assert summary[1]['crank']and summary[1]['qualified']and summary[1]['reason']=='cranking_spark_bypass'and not summary[1]['faults']and not summary[1]['active']
assert summary[2]['active']and not summary[2]['faults']
assert summary[3]['faults']and summary[3]['reason']=='input_time_reversed'
assert not summary[4]['faults']and summary[4]['reason']=='cranking_spark_bypass'and not summary[4]['qualified']
assert summary[5]['faults']and summary[5]['reason']=='input_initial_qualification'
assert summary[6]['active']and not summary[6]['faults']
(OUT/(PHASE+'-runtime-records.json')).write_text(json.dumps(records,indent=2)+'\n')
(OUT/(PHASE+'-runtime-fixture.json')).write_text(json.dumps(dict(header=header,page=page,summary=summary),indent=2)+'\n')
(OUT/(PHASE+'-native.msl')).write_text(msl)
(OUT/(PHASE+'-runtime-build.json')).write_text(json.dumps(dict(commands=commands,passed=True,records=len(records),summary=summary),indent=2)+'\n')
print(json.dumps(summary,indent=2))
