#include "ecu/engine_radio_health.hpp"
#include <cassert>
#include <iostream>
using namespace ecu;
static unsigned checks=0;
static void verify(bool v,const char*expression,unsigned line){++checks;if(!v)std::cerr<<line<<": "<<expression<<'\n';assert(v);}
#define check(v) verify((v),#v,__LINE__)
static engine::RuntimeSample captured(){
 engine::Tune t;t.flex_fuel.input_confirmed=true;t.flex_fuel.correction.enabled=true;t.flex_fuel.capture.cycles=2;
 flex::Capture c(t.flex_fuel.capture);c.edge(1000,true,flex::Source::TargetCapture);
 for(unsigned n=1;n<=2;++n){c.edge(1000+n*10000-3000,false,flex::Source::TargetCapture);c.edge(1000+n*10000,true,flex::Source::TargetCapture);}
 engine::Inputs in;in.rpm=0;in.map_kpa=50;in.tps_pct=10;in.clt_c=85;in.iat_c=25;in.lambda=1;in.battery_v=14;in.sensor_v=5;in.sensors_valid=in.lambda_ready=true;in.sampled_us=21000;in.flex_sample={c.observe(21000),t.flex_fuel.capture,t.revision};
 engine::Controller controller;const auto output=controller.step(t,in,21000);
 auto r=engine::synthetic_data(t,in,output,1,21000);r.source=engine::DataSource::Target;return r;
}
static void age_and_indicator(){
 auto r=captured();check(r.flex_fuel.has(flex::RawQualified)&&r.inputs[engine::DecodedRpm]==0);
 check(radio::wire::flex_sample_age(r,21000)==0);check(!radio::required_flex_problem(r,0,0));
 check(!radio::required_flex_problem(r,250000,20000));check(radio::required_flex_problem(r,250001,20000));
 check(radio::required_flex_problem(r,UINT64_MAX,0));check(radio::required_flex_problem(r,0,UINT64_MAX));check(radio::required_flex_problem(r,0,1000001));
 check(radio::wire::flex_sample_age(r,20999)==UINT64_MAX);
 auto bad=r;bad.flex_fuel.flags&=~flex::ControlOk;check(radio::required_flex_problem(bad,0,0));
 bad=r;bad.flex_fuel.flags|=flex::PendingFault;check(radio::required_flex_problem(bad,0,0));
 bad=r;bad.flex_fuel.revision++;check(radio::required_flex_problem(bad,0,0));
 bad=r;bad.flex_fuel.source=2;check(radio::required_flex_problem(bad,0,0));check(!radio::wire::engine_schema_supports(5,bad));
 for(unsigned n=0;n<1000;++n){auto off=r;off.flex_fuel.flags&=~(flex::Required|flex::CorrectionsEnabled);check(!radio::required_flex_problem(off,n*5000,UINT64_MAX));}
 // A first raw edge has no completed timestamp. Scalar host epoch0 is valid.
 auto acquiring=r;acquiring.flex_fuel.times[0]=0;acquiring.flex_fuel.flags&=~(flex::SampleValueValid|flex::CaptureValid|flex::ValueQualified|flex::RawQualified|flex::ControlOk|flex::CorrectionsValid);
 check(radio::wire::flex_sample_age(acquiring,1000000)==UINT64_MAX);
 check(!flex::sample_timestamp_known(flex::Source::TargetCapture,0,false));check(flex::sample_timestamp_known(flex::Source::SyntheticValue,0,true));
 auto invalid=r;invalid.flex_fuel.values[6]=1000;check(!flex::valid_record(invalid.flex_fuel));
}
static void immutable_pair(){
 using namespace radio::wire;auto r=captured();EnginePair pair;
 // Deterministic test MAC only; actual OpenSSL/Python MAC equality is tested
 // independently through the native radio fixture adapter.
 unsigned mac_calls=0;
 auto mac=[&](const std::uint8_t*p,unsigned n,std::uint8_t*out){++mac_calls;for(unsigned j=0;j<32;++j){out[j]=j;for(unsigned i=j;i<n;i+=32)out[j]^=p[i];}return true;};
 check(pair.prepare(r,7,8,0,0,UINT32_MAX,0,5000000,mac));check(mac_calls==2&&pair.pending()&&!pair.base_submitted()&&pair.size()==250);
 std::array<std::uint8_t,250> base;std::memcpy(base.data(),pair.data(),250);
 check(!pair.prepare(r,7,9,0,0,0,0,5000001,mac));check(mac_calls==2&&pair.sequence()==8);
 r.flex_fuel.values[2]=99;r.flex_fuel.revision=2; // New live data cannot alter the pending extension.
 check(!pair.submitted()&&pair.pending()&&pair.base_submitted()&&pair.size()==232);
 check(same(pair.data()+24,base.data()+218,32));check(read32(pair.data()+180)==1&&read64(pair.data()+56)==21000);
 check(read32(pair.data()+192)==0&&read32(pair.data()+196)==250000);
 check(!pair.expired(5250000)&&pair.expired(5250001)&&pair.expired(4999999));
 check(pair.submitted()&&!pair.pending()&&pair.data()==nullptr&&pair.size()==0);check(pair.prepared_us()==5000000&&pair.sequence()==8);
 check(!pair.submitted());pair.cancel();check(!pair.pending());
 auto original=captured();check(pair.prepare(original,7,10,0,0,0,0,UINT64_MAX-10,mac));check(!pair.expired(UINT64_MAX));check(pair.expired(0));pair.cancel();
 check(!pair.prepare(original,7,11,0,0,0,0,0,[](auto,auto,auto){return false;}));check(!pair.pending());
 for(unsigned schema=1;schema<=4;++schema)check(!engine_schema_supports(schema,original));
 original.flex_fuel=flex::Record{};for(unsigned schema=1;schema<=5;++schema)check(engine_schema_supports(schema,original));
 check(pair.prepare(original,7,12,0,0,0,UINT32_MAX,0,mac));pair.cancel();
 check(!pair.prepare(original,7,13,0,0,0,0,0,mac)); // Never turn unavailable data into age0.
 auto unknown=captured();unknown.flex_fuel.flags&=~(flex::RawQualified|flex::ValueQualified|flex::CaptureValid|flex::SampleValueValid|flex::ControlOk|flex::CorrectionsValid);
 const std::uint32_t nan_bits=0xffc01234;std::memcpy(&unknown.flex_fuel.values[0],&nan_bits,4);
 check(pair.prepare(unknown,7,14,0,0,0,0,0,mac));pair.submitted();check(read32(pair.data()+112)==0x7fc00000);pair.cancel();
}
static_assert(sizeof(radio::wire::EnginePair)<=912,"Bounded per-peer observation storage");
int main(){age_and_indicator();immutable_pair();std::cout<<"engine_radio_flex_checks "<<checks<<'\n';}
