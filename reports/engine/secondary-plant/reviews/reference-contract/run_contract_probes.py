#!/usr/bin/env python3
"""Independent production-loop contract probes; no coupled-plant acceptance."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
UPSTREAM = ROOT.parent / 'speeduino'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build():
    cache = ROOT / '.cache/engine/speeduino-sim'
    manifest = json.loads((cache / 'build-manifest.json').read_text())
    # Snapshot known objects before the implementation agent updates its cache.
    objdir = OUT / 'objects'
    objdir.mkdir(exist_ok=True)
    objects = []
    for obj in sorted((cache / 'obj').glob('*.o')):
        if obj.name == 'tools_speeduino_sim.cpp.o':
            continue
        copied = objdir / obj.name
        shutil.copy2(obj, copied)
        objects.append(copied)
    original = subprocess.check_output(['git', '-C', str(ROOT), 'show', 'HEAD:tools/speeduino_sim.cpp'], text=True)
    inject = r'''
    // Review-only fixture is persisted before the unchanged production setup.
    auto setting=[](const char* name, unsigned fallback) {
        auto* s=std::getenv(name);return s?unsigned(std::stoul(s)):fallback;
    };
    for(unsigned n=0;n<16;++n){
        fuelTable2.axisX[n]=ignitionTable2.axisX[n]=(n+1)*5;
        fuelTable2.axisY[n]=ignitionTable2.axisY[n]=(n+1)*8;
    }
    fuelTable2.values.fill(setting("REVIEW_FCELL",110));
    ignitionTable2.values.fill(setting("REVIEW_SCELL",60));
    configPage10.fuel2Mode=setting("REVIEW_FMODE",0);
    configPage10.spark2Mode=setting("REVIEW_SMODE",0);
    configPage10.fuel2Algorithm=configPage10.spark2Algorithm=static_cast<LoadSource>(setting("REVIEW_SOURCE",0));
    configPage10.fuel2SwitchVariable=configPage10.spark2SwitchVariable=setting("REVIEW_CONDITION",0);
    configPage10.fuel2SwitchValue=configPage10.spark2SwitchValue=setting("REVIEW_THRESHOLD",1000);
    configPage10.fuel2InputPin=setting("REVIEW_FPIN",14);configPage10.spark2InputPin=setting("REVIEW_SPIN",15);
    configPage10.fuel2InputPolarity=1;configPage10.spark2InputPolarity=1;
    configPage10.fuel2InputPullup=0;configPage10.spark2InputPullup=0;
'''
    marker='    // Persist through the real storage API, then let unmodified setup load it.'
    assert original.count(marker)==1
    source = original.replace(marker,inject+'\n'+marker)
    extra = r'''
            else if(command=="reviewgpio") {
                unsigned fuel,spark;std::cin>>fuel>>spark;
                if(fuel>1||spark>1)throw std::runtime_error("review GPIO level");
                pins[pinNumbers.pinFuel2Input]=fuel;pins[pinNumbers.pinSpark2Input]=spark;
                loop();
            }
            else if(command=="reviewstatus") {
                std::cout<<"reviewstatus "<<speeduino_sim_micros()<<' '<<currentStatus.RPM<<' '<<currentStatus.MAP<<' '
                    <<unsigned(currentStatus.TPS)<<' '<<unsigned(currentStatus.VE1)<<' '<<unsigned(currentStatus.VE2)<<' '<<unsigned(currentStatus.VE)<<' '
                    <<int(currentStatus.advance1)<<' '<<int(currentStatus.advance2)<<' '<<int(currentStatus.advance)<<' '
                    <<currentStatus.secondFuelTableActive<<' '<<currentStatus.secondSparkTableActive<<' '
                    <<unsigned(configPage10.fuel2Mode)<<' '<<unsigned(configPage10.spark2Mode)<<' '
                    <<unsigned(pinNumbers.pinFuel2Input)<<' '<<unsigned(pinNumbers.pinSpark2Input)<<' '
                    <<digitalRead(pinNumbers.pinFuel2Input)<<' '<<digitalRead(pinNumbers.pinSpark2Input)<<' '
                    <<fuelSchedule1.pw<<' '<<unsigned(currentStatus.rotationStatus)<<' '
                    <<unsigned(configPage10.fuel2InputPin)<<' '<<unsigned(configPage10.spark2InputPin)<<' '<<unsigned(BOARD_MAX_IO_PINS)<<'\n';
            }
'''
    marker='            else if (command == "status") status();'
    assert source.count(marker)==1
    source=source.replace(marker,extra+'\n'+marker)
    wrapper=OUT/'probe_adapter.cpp'
    wrapper.write_text(source)
    wrapper_obj=OUT/'probe_adapter.o'
    flags=manifest['compile_flags']
    subprocess.run(['c++',*flags,'-x','c++','-c',str(wrapper),'-o',str(wrapper_obj)],check=True,capture_output=True)
    libraries=[UPSTREAM/p for p in manifest['dependency_hashes'] if p.endswith('.a')]
    executable=OUT/'production-loop-probe'
    subprocess.run(['c++',*map(str,objects),str(wrapper_obj),'-Wl,--start-group',*map(str,libraries),'-Wl,--end-group','-lgcov','-pthread','-o',str(executable)],check=True,capture_output=True)
    record=dict(base_manifest=manifest,base_wrapper_sha256=hashlib.sha256(original.encode()).hexdigest(),review_wrapper_sha256=sha(wrapper),binary_sha256=sha(executable),objects={p.name:sha(p) for p in objects},limits=['review-only configuration and GPIO fixture','actual pinned production setup/loop/sensors/calculations/schedulers','fixed shaft-tooth diagnostic input; no external plant and no engine acceptance','native32 timer HAL; zero CPU/IRQ cost; virtual GPIO only'])
    (OUT/'probe-build.json').write_text(json.dumps(record,indent=2)+'\n')
    return executable


def run(executable,name,settings,commands):
    env=dict(os.environ,**{'REVIEW_'+k:str(v) for k,v in settings.items()})
    script='\n'.join([*commands,'quit',''])
    result=subprocess.run([str(executable)],input=script,text=True,env=env,capture_output=True,timeout=30,check=True)
    (OUT/(name+'.txt')).write_text(result.stdout)
    rows=[list(map(int,l.split()[1:])) for l in result.stdout.splitlines() if l.startswith('reviewstatus ')]
    return dict(settings=settings,commands=commands,rows=[dict(zip(('time_us','rpm','map_kpa','tps_half_pct','ve1','ve2','ve','advance1','advance2_encoded','advance','fuel_active','spark_active','fuel_mode','spark_mode','fuel_pin','spark_pin','fuel_level','spark_level','pw1_us','rotation','raw_fuel_pin','raw_spark_pin','board_max_io_pins'),r)) for r in rows],edge_count=sum(l.startswith('edge ') for l in result.stdout.splitlines()))


def teeth(rpm,duration_us):
    period=round(1e6/rpm)
    return ['tooth '+str(t) for n in range(1,duration_us//period+1) if n%60<58 for t in [n*period]]


if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    executable=build()
    probes={}
    probes['unrepresentable_native_pins']=run(executable,'unrepresentable_native_pins',dict(FMODE=4,SMODE=4,FPIN=30,SPIN=31),['advance 0','reviewstatus','reviewgpio 1 0','reviewstatus','reviewgpio 0 1','reviewstatus'])
    probes['input_independence']=run(executable,'input_independence',dict(FMODE=4,SMODE=4),['advance 0','reviewstatus','reviewgpio 1 0','reviewstatus','reviewgpio 0 1','reviewstatus','reviewgpio 1 1','reviewstatus'])
    probes['tps_strict_boundary']=run(executable,'tps_strict_boundary',dict(FMODE=3,SMODE=3,CONDITION=2,THRESHOLD=20),['sensors 100 10.5 85 25 14 14.7','advance 35000','reviewstatus','sensors 100 11 85 25 14 14.7','advance 70000','reviewstatus'])
    probes['multiply_running']=run(executable,'multiply_running',dict(FMODE=1,SMODE=1,FCELL=150,SCELL=190),[*teeth(1000,1200000),'reviewstatus'])
    probes['zero_fuel_running']=run(executable,'zero_fuel_running',dict(FMODE=1,FCELL=0),[*teeth(1000,1200000),'reviewstatus'])
    probes['cranking_spark_bypass']=run(executable,'cranking_spark_bypass',dict(FMODE=1,SMODE=1,FCELL=150,SCELL=190),[*teeth(200,1200000),'reviewstatus'])
    probes['wide_spark_add']=run(executable,'wide_spark_add',dict(FMODE=2,SMODE=2,FCELL=250,SCELL=0),[*teeth(1000,1200000),'reviewstatus'])
    assert [(r['fuel_active'],r['spark_active']) for r in probes['input_independence']['rows']]==[(0,0),(1,0),(0,1),(1,1)]
    assert [(r['fuel_pin'],r['spark_pin']) for r in probes['unrepresentable_native_pins']['rows']]==[(0,0)]*3
    assert [(r['tps_half_pct'],r['fuel_active']) for r in probes['tps_strict_boundary']['rows']]==[(20,0),(21,1)]
    r=probes['multiply_running']['rows'][0]
    assert (r['rpm'],r['ve1'],r['ve2'],r['ve'],r['advance1'],r['advance2_encoded'],r['advance'])==(1000,85,150,128,10,23,15)
    r=probes['zero_fuel_running']['rows'][0]
    assert r['ve']==0 and r['pw1_us']==900 and probes['zero_fuel_running']['edge_count']>0
    r=probes['cranking_spark_bypass']['rows'][0]
    assert r['rpm']==200 and r['spark_active']==0 and r['advance']==5
    r=probes['wide_spark_add']['rows'][0]
    assert r['ve']==255 and r['advance']==-30
    (OUT/'probe-results.json').write_text(json.dumps(dict(scope='Independent production-loop contract probes, not coupled external-plant acceptance',probes=probes),indent=2)+'\n')
    print(json.dumps({name:dict(rows=p['rows'],edge_count=p['edge_count']) for name,p in probes.items()},indent=2))
