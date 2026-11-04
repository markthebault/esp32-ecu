"""Native ABI for the same bounded dispatcher compiled into the ESP32 ISR."""
import ctypes
import fcntl
import os
from pathlib import Path
import subprocess
from engine_runtime import EngineRuntime,R
import threading

_build_lock=threading.Lock()


def load_target_bridge():
    with _build_lock:
        cache=R/'.cache/engine/target-native';cache.mkdir(parents=True,exist_ok=True)
        cjson=Path.home()/'.platformio/packages/framework-espidf/components/json/cJSON'
        source=R/'tools/target_timing_bridge.cpp'
        dependencies=[Path(__file__),source,R/'firmware/main/config_json.hpp',cjson/'cJSON.c',cjson/'cJSON.h',
                      *sorted((R/'firmware/include/ecu').glob('*.hpp'))]
        library=cache/'libtarget_engine.so'
        with (cache/'build.lock').open('a+b') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            if not library.exists() or max(p.stat().st_mtime for p in dependencies)>library.stat().st_mtime:
                subprocess.run(['cc','-O2','-fPIC','-c',str(cjson/'cJSON.c'),'-o',str(cache/'cJSON.o')],check=True)
                subprocess.run(['c++','-std=c++17','-O2','-Wall','-Wextra','-Werror','-shared','-fPIC',
                                '-I'+str(cjson),'-I'+str(R/'firmware/main'),'-I'+str(R/'firmware/include'),
                                str(source),str(cache/'cJSON.o'),'-o',str(cache/'libtarget_engine.new.so')],check=True)
                os.replace(cache/'libtarget_engine.new.so',library)
        bridge=ctypes.CDLL(str(library))
        P=ctypes.c_void_p;U=ctypes.c_uint64;S=ctypes.c_char_p;I=ctypes.c_uint
        signatures={'engine_create':([],P),'engine_destroy':([P],None),'engine_validate':([S],ctypes.c_int),
                    'engine_canonicalize':([S],S),'engine_configure':([P,S],ctypes.c_int),'engine_wheel':([P,I,I,I],ctypes.c_int),
                    'engine_cam':([P,U],ctypes.c_int),'engine_trigger':([P,U],ctypes.c_int),'engine_step':([P,S,U,U],S),
                    'engine_cut':([P],None),'engine_timing_reason':([P],S),'engine_next_time':([P],U),
                    'engine_progress':([P,U],None),
                    'engine_pop':([P],I),'engine_event_dwell':([P],U),'engine_event_advance':([P],ctypes.c_double),
                    'engine_data_json':([P],S),'engine_idle_json':([P],S),'engine_plan':([P],S)}
        for name,(args,result) in signatures.items():
            fn=getattr(bridge,name);fn.argtypes=args;fn.restype=result
        return bridge


class TargetRuntime(EngineRuntime):
    def __init__(self,tune=None):super().__init__(tune,load_target_bridge())
    def progress(self,time_us):self.bridge.engine_progress(self.handle,time_us)
    def idle_status(self):
        import json
        return json.loads(self.bridge.engine_idle_json(self.handle))
