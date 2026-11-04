#!/usr/bin/env python3
"""Package the reviewable A0 sources, CAD, reports and monitor binaries."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]
REPORTS=ROOT/"reports"
BUILD=ROOT/"build"
BUILD.mkdir(exist_ok=True)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


erc=json.loads((REPORTS/"erc.json").read_text())
drc=json.loads((REPORTS/"drc.json").read_text())
assert not [v for s in erc["sheets"] for v in s.get("violations",[])], "ERC must pass"
assert not drc["violations"] and not drc["unconnected_items"] and not drc["schematic_parity"], "DRC/parity must pass"
log=(ROOT/".cache/firmware-build.log").read_text()
builds={}
for env in ["esp32s3","bench"]:
    assert re.search(r"^"+env+r"\s+SUCCESS",log,re.M), env+" build missing"
    binary=ROOT/f"firmware/.pio/build/{env}/firmware.bin"
    config=json.loads((ROOT/f"firmware/.pio/build/{env}/config/sdkconfig.json").read_text())
    for key in ["GPIO_CTRL_FUNC_IN_IRAM","GPTIMER_ISR_CACHE_SAFE","GPTIMER_CTRL_FUNC_IN_IRAM","MCPWM_ISR_CACHE_SAFE"]:
        assert config.get(key) is True
    builds[env]={"compiled":True,"hardware_executed":False,"firmware_sha256":sha(binary),"firmware_bytes":binary.stat().st_size}
    builds[env]["bench_trigger_profile"]={
        "wheel_slots":config.get("ECU_TRIGGER_SLOTS"),
        "missing_teeth":config.get("ECU_TRIGGER_MISSING"),
        "capture_speed_ceiling_rpm":config.get("ECU_CAPTURE_MAX_RPM"),
    }
(REPORTS/"firmware-build.json").write_text(json.dumps({"platform":"espressif32@6.12.0","framework":"ESP-IDF 5.5.0","target":"ESP32-S3","environments":builds},indent=2)+"\n")
test_output=(REPORTS/"firmware-tests.txt").read_text()
scenarios=int(re.search(r"(\d+) control scenarios passed",test_output).group(1))
contract=json.loads((ROOT/"hardware/net_contract.json").read_text())
summary={
    "generated_utc":datetime.now(timezone.utc).isoformat(),"revision":"A0","stage":"bench_development_prototype",
    "cad":{"kicad":drc["kicad_version"],"schematic_pages":8,"pcb_layers":4,"board_mm":[200,200],
           "parts_including_mounting_holes":len(contract["parts"]),"erc_violations":0,"drc_violations":0,"unconnected_items":0,"schematic_parity_issues":0},
    "software":{"host_scenarios":scenarios,"address_and_undefined_behavior_sanitizers":True,"builds":builds},
    "manufacturing_release":False,"vehicle_release":False,"engine_scheduling_in_flashable_image":False,
    "physical_tests_performed":[],
    "platform_scope":{"generic_core":True,"specific_car_required_for_platform_development":False,
                      "hardware_class":"A0_12V_PFI4_HIGH_IMPEDANCE_SMART_COILS_HALL",
                      "configurable_bench_trigger":True,"full_engine_profile_loader":False},
    "open_requirements":["Generic profile-driven engine scheduling and calibration interfaces","Exact BOM/footprint and assembly release review",
       "Measured supply, transient, EMC, thermal and timing qualification","Engine scheduling backend and sensor calibration",
       "Fuel/ignition calibration, misfire and catalyst protection","Later installation: adapter, OEM interfaces and vehicle commissioning"],
    "generic_bom_references":[p["ref"] for p in contract["parts"] if not p["mpn"]],
}
(REPORTS/"validation-summary.json").write_text(json.dumps(summary,indent=2)+"\n")
(REPORTS/"firmware-build.txt").write_text("ESP32-S3 / espressif32@6.12.0 / ESP-IDF 5.5.0\n"+"\n".join(f'{e}: compiled, {b["firmware_bytes"]} bytes, SHA256 {b["firmware_sha256"]}; not executed on hardware' for e,b in builds.items())+"\n")
release=BUILD/"monitor-firmware"
release.mkdir(exist_ok=True)
for name in ["firmware.bin","bootloader.bin","partitions.bin"]:
    shutil.copyfile(ROOT/"firmware/.pio/build/esp32s3"/name,release/name)
(release/"README.txt").write_text("A0 bench MONITOR firmware. Outputs inhibited. No engine scheduling.\nUse PlatformIO with the matching source project to flash; it supplies the correct offsets.\nNot executed on hardware; no vehicle qualification.\n")
files=[ROOT/"README.md",ROOT/".gitignore"]
for folder in ["hardware","docs","scripts","firmware","reports"]:
    for path in (ROOT/folder).rglob("*"):
        if not path.is_file():continue
        relative=path.relative_to(ROOT)
        if any(x in relative.parts for x in [".pio","__pycache__"]):continue
        if path.suffix in [".kicad_prl",".lck",".pyc"]:continue
        if path.name.startswith("sdkconfig.") and path.name!="sdkconfig.defaults":continue
        files.append(path)
manifest={str(p.relative_to(ROOT)):sha(p) for p in sorted(files)}
manifest.update({"monitor-firmware/"+p.name:sha(p) for p in release.iterdir() if p.is_file()})
archive=BUILD/"esp32-ecu-a0.zip"
with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED) as z:
    for path in sorted(files):z.write(path,"esp32-ecu-a0/"+str(path.relative_to(ROOT)))
    for path in release.iterdir():z.write(path,"esp32-ecu-a0/monitor-firmware/"+path.name)
    z.writestr("esp32-ecu-a0/SHA256.json",json.dumps(manifest,indent=2)+"\n")
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for path,digest in manifest.items():
        assert hashlib.sha256(z.read("esp32-ecu-a0/"+path)).hexdigest()==digest
print(f"Packaged {len(files)} source/CAD/report files and monitor firmware; ZIP integrity and SHA256 verified: {archive}")
