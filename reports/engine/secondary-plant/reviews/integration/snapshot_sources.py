import datetime, hashlib, json, pathlib, shutil, subprocess, sys
root=pathlib.Path(__file__).resolve().parents[3]
base=pathlib.Path(__file__).resolve().parent
name=sys.argv[1]
out=base/name
out.mkdir(parents=True,exist_ok=False)
paths=[*sorted(root.glob('firmware/include/ecu/*.hpp')),*sorted(root.glob('tools/*secondary*')),root/'tools/compare_engine_controllers.py',root/'tools/switch_acquisition_bridge.cpp',root/'tools/switch_acquisition_runtime.py',root/'tools/engine_research_plant.py',root/'tools/engine_runtime.py',root/'tools/engine_bridge.cpp',root/'tools/target_runtime.py',root/'tools/target_timing_bridge.cpp',root/'tools/speeduino_runtime.py',root/'tools/speeduino_sim.cpp',root/'tools/speeduino_sim_hal.cpp',root/'tools/speeduino_sim_native.hpp',root/'scripts/build_speeduino_sim.py',root/'simulation/modelica/EngineAirPath.mo',root/'config/engine/defaults.json',root/'firmware/main/switch_service.cpp',root/'firmware/main/app.cpp']
hashes={}
for p in paths:
 if not p.is_file(): continue
 rel=p.relative_to(root);dest=out/'sources'/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest);hashes[str(rel)]=hashlib.sha256(p.read_bytes()).hexdigest()
for bits,folder in ((32,'speeduino-sim'),(16,'speeduino-sim16')):
 p=root/'.cache/engine'/folder/'build-manifest.json'
 if p.exists():shutil.copy2(p,out/(folder+'-manifest.json'))
upstream=root.parent/'speeduino'
manifest=dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),project_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),project_status=subprocess.check_output(['git','status','--short'],cwd=root,text=True),reference_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=upstream,text=True).strip(),reference_status=subprocess.check_output(['git','status','--short'],cwd=upstream,text=True),source_hashes=hashes)
(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(out)
