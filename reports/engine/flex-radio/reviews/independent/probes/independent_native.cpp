#include "ecu/engine_radio_health.hpp"
#include <openssl/hmac.h>
#include <cassert>
#include <cstdio>
#include <iostream>
#include <iomanip>
#include <string>
using namespace ecu;
namespace w=ecu::radio::wire;
static unsigned checks=0;
static void check(bool b){++checks;assert(b);}
static bool mac(const std::uint8_t*p,unsigned n,std::uint8_t*out){std::uint8_t lmk[16],boot[16],key[32];for(unsigned i=0;i<16;++i){lmk[i]=i;boot[i]=16+i;}const auto t=w::engine_key_transcript(boot,0x12345678);unsigned size=0;return HMAC(EVP_sha256(),lmk,16,t.data(),t.size(),key,&size)&&size==32&&HMAC(EVP_sha256(),key,32,p,n,out,&size)&&size==32;}
static std::string hex(const std::uint8_t*p,unsigned n){static const char h[]="0123456789abcdef";std::string s;s.reserve(2*n);for(unsigned i=0;i<n;++i){s+=h[p[i]>>4];s+=h[p[i]&15];}return s;}
static flex::Record raw_record(flex::Source source=flex::Source::TargetCapture,std::uint64_t shift=0,std::uint64_t query=24500){
 flex::Config cfg;cfg.capture.cycles=2;cfg.correction.enabled=true;cfg.input_confirmed=true;
 flex::Capture c(cfg.capture);c.edge(shift+1000,true,source);c.edge(shift+8000,false,source);c.edge(shift+11000,true,source);c.edge(shift+18000,false,source);c.edge(shift+21000,true,source);
 return flex::record(flex::assess(cfg,{c.observe(shift+query),cfg.capture,7},shift+query,true,7));
}
static engine::RuntimeSample runtime(const flex::Record&f,unsigned n=0){
 engine::RuntimeSample r;r.sequence=100+n;r.source=f.source==2||f.source==3?engine::DataSource::Synthetic:engine::DataSource::Target;r.tune_revision=7;r.sensor_revision=9;r.phase_epoch=3;r.worker_epoch=4;r.worker_sequence=2;r.worker_tune_revision=7;r.worker_sensor_revision=9;
 r.flags=engine::Present|engine::StorageOk|engine::InputsFresh|engine::InputsQualified;r.state=2;r.strategy=2;r.input_valid=255;r.phase_reason=0;r.board_flags=0;r.cam_error_deg=NAN;
 const float inputs[]={0,50,10,85,25,1,14,5};for(unsigned i=0;i<8;++i)r.inputs[i]=inputs[i];for(unsigned i=0;i<14;++i)r.proposals[i]=float(i)/4;r.flex_fuel=f;return r;
}
static void number(float f){if(std::isfinite(f))std::cout<<std::setprecision(9)<<f;else std::cout<<"null";}
static void emit(const char*name,const flex::Record&f,unsigned n,std::uint32_t age=8,std::uint32_t control=4){
 auto r=runtime(f,n);check(flex::valid_record(f));w::EnginePair pair;check(pair.prepare(r,0x12345678,10+n,0,control,UINT32_MAX,age,5030000+1000*n,mac));
 const std::string base=hex(pair.data(),pair.size());check(!pair.submitted());const std::string extension=hex(pair.data(),pair.size());check(pair.submitted());
 std::cout<<"{\"name\":\""<<name<<"\",\"base\":\""<<base<<"\",\"extension\":\""<<extension<<"\",\"record\":{\"times\":[";
 for(unsigned i=0;i<7;++i){if(i)std::cout<<',';std::cout<<'\"'<<f.times[i]<<'\"';}std::cout<<"],\"values\":[";
 for(unsigned i=0;i<10;++i){if(i)std::cout<<',';number(f.values[i]);}std::cout<<"],\"calibration\":[";for(unsigned i=0;i<6;++i){if(i)std::cout<<',';number(f.calibration[i]);}
 std::cout<<"],\"flags\":"<<f.flags<<",\"revision\":"<<f.revision<<",\"codes\":[";const unsigned char codes[]={f.source,f.reason,f.capture_reason,f.last_fault,f.correction_reason,f.window_cycles,f.calibration_cycles};for(unsigned i=0;i<7;++i){if(i)std::cout<<',';std::cout<<unsigned(codes[i]);}std::cout<<"]}}\n";
}
int main(){
 auto f=raw_record();check(f.has(flex::ValueQualified)&&f.has(flex::ControlOk));auto r=runtime(f);
 check(w::flex_sample_age(r,21000)==0);check(w::flex_sample_age(r,20999)==UINT64_MAX);check(!radio::required_flex_problem(r,250000,1000000));check(radio::required_flex_problem(r,250001,0));check(radio::required_flex_problem(r,0,1000001));check(radio::required_flex_problem(r,UINT64_MAX,0));
 for(unsigned i=0;i<32;++i){auto b=r;if(i&1)b.flex_fuel.flags&=~flex::ControlOk;if(i&2)b.flex_fuel.flags|=flex::PendingFault;if(i&4)b.flex_fuel.revision++;if(i&8)b.flex_fuel.times[4]++;if(i&16)b.flex_fuel.source=2;check(radio::required_flex_problem(b,0,0)==bool(i));}
 for(unsigned i=0;i<1000;++i){auto off=r;off.flex_fuel.flags&=~(flex::Required|flex::CorrectionsEnabled);check(!radio::required_flex_problem(off,UINT64_MAX,UINT64_MAX));}
 for(unsigned fail=0;fail<2;++fail){w::EnginePair p;unsigned calls=0;check(!p.prepare(r,1,1,0,0,0,0,0,[&](auto,auto,auto){return calls++!=fail;}));check(!p.pending()&&p.size()==0&&p.data()==nullptr);}
 w::EnginePair p;check(p.prepare(r,1,1,0,0,0,0,UINT64_MAX-10,mac));auto bytes=hex(p.data(),p.size());check(!p.prepare(runtime(f,1),1,2,0,0,0,0,0,mac));check(hex(p.data(),p.size())==bytes);check(!p.expired(UINT64_MAX)&&p.expired(0));check(!p.submitted());bytes=hex(p.data(),p.size());check(hex(p.data(),p.size())==bytes);p.cancel();check(!p.pending()&&!p.submitted());
 emit("target_raw",f,0);emit("synthetic_raw",raw_record(flex::Source::Synthetic),1);emit("u64_raw",raw_record(flex::Source::TargetCapture,UINT64_C(9007199254740993)),2);
 emit("absent",flex::Record{},3,UINT32_MAX);
 flex::Config cfg;cfg.capture.cycles=2;cfg.input_confirmed=true;cfg.correction.enabled=true;flex::Capture c(cfg.capture);c.edge(1000,true,flex::Source::TargetCapture);auto a=flex::record(flex::assess(cfg,{c.observe(24500),cfg.capture,7},24500,true,7));check(std::isnan(a.values[6]));check(w::flex_sample_age(runtime(a),1000000)==UINT64_MAX);emit("acquiring",a,4,UINT32_MAX);
 auto stale=raw_record(flex::Source::TargetCapture,0,300000);check(!stale.has(flex::ValueQualified));emit("stale",stale,5,283,4);
 cfg.correction.enabled=false;auto scalar=flex::record(flex::assess(cfg,flex::synthetic_value(37.5,true,0,cfg.capture,7),0,true,7));check(scalar.has(flex::ValueQualified)&&std::isfinite(scalar.values[6]));check(w::flex_sample_age(runtime(scalar),0)==0);emit("scalar_epoch_zero",scalar,6,0,0);
 auto malformed=r;malformed.flex_fuel.source=2;check(!w::engine_schema_supports(5,malformed));
 for(unsigned schema=1;schema<=4;++schema)check(!w::engine_schema_supports(schema,r));
 std::cerr<<"independent_native_checks "<<checks<<'\n';
}
