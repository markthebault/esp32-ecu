from pathlib import Path
import hashlib,json,os,subprocess,sys
own=Path(__file__).resolve().parent;freeze=own/'freeze-final-001';out=own/('sender-'+(sys.argv[1]if len(sys.argv)>1 else'001'));out.mkdir(exist_ok=False);(out/'fixtures').mkdir()
env={**os.environ,'GCOV_PREFIX':str(own/'gcov'),'GCOV_PREFIX_STRIP':'0','ASAN_OPTIONS':'detect_leaks=1','UBSAN_OPTIONS':'halt_on_error=1','PYTHONDONTWRITEBYTECODE':'1'}
flags=['-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer'];includes=['-I'+str(freeze/p)for p in ('external/cJSON','firmware/tests/radio_fakes','firmware/tests/target_fakes','firmware/tests','firmware/include')]
cjson=out/'cjson.o';common=['c++','-std=c++17',*flags,'-Wall','-Wextra','-Werror','-pedantic','-pthread','-DECU_COMPACT_A3=1','-DECU_SELECTED_N16R8=1','-DECU_FLEX_G38_DRAFT=1',*includes]
commands=[['cc',*flags,'-c',str(freeze/'external/cJSON/cJSON.c'),'-o',str(cjson)]]
for stem,source in [('parent-service',freeze/'firmware/tests/radio_service_test.cpp'),('independent-service',own/'probes/independent_sender.cpp'),('parent-pair',freeze/'firmware/tests/engine_radio_flex_test.cpp')]:
 commands += [[*common,'-MMD','-MF',str(out/(stem+'.d')),str(source),str(cjson),'-lcrypto','-o',str(out/stem)], [str(out/stem),*([str(out/'fixtures')]if stem=='parent-service'else[])]]
report={'environment':{k:env[k]for k in ('GCOV_PREFIX','GCOV_PREFIX_STRIP','ASAN_OPTIONS','UBSAN_OPTIONS','PYTHONDONTWRITEBYTECODE')},'commands':[]}
for i,cmd in enumerate(commands):
 r=subprocess.run(cmd,env=env,capture_output=True);log=out/(str(i)+'.log');log.write_bytes(r.stdout+r.stderr);report['commands'].append({'command':cmd,'returncode':r.returncode,'stdout_sha256':hashlib.sha256(r.stdout).hexdigest(),'stderr_sha256':hashlib.sha256(r.stderr).hexdigest(),'log':str(log.relative_to(own))});(out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
 if r.returncode:print(json.dumps(report['commands'][-1]));sys.exit(r.returncode)
print(json.dumps({'passed':True,'commands':len(commands),'receipt':str((out/'receipt.json').relative_to(own))}))
