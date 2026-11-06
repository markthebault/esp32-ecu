#include "ecu/engine_radio_flex.hpp"
#include <cassert>
#include <iostream>
using namespace ecu;
using namespace ecu::radio::wire;
static unsigned checks=0;
static void verify(bool v,const char*expression,unsigned line){++checks;if(!v)std::cerr<<line<<": "<<expression<<'\n';assert(v);}
#define check(v) verify((v),#v,__LINE__)
static engine::RuntimeSample observation(double pressure=150){
 engine::Tune t;t.injector_cc_min=600;t.dfco_enabled=false;t.boost_control.pressure_enabled=true;t.boost_control.mode=boost::Mode::OpenLoop;t.boost_control.open_duty.cells.fill(40);
 engine::Inputs in;in.rpm=2000;in.map_kpa=pressure;in.tps_pct=50;in.clt_c=85;in.iat_c=25;in.lambda=1;in.battery_v=14;in.sensor_v=5;
 in.synced=in.phase_synced=in.sensors_valid=in.lambda_ready=true;in.sampled_us=1000000;
 engine::Controller c;auto out=c.step(t,in,1000000);return engine::synthetic_data(t,in,out,1,1000000);
}
static void multipart(){
 auto r=observation();EnginePair parts;unsigned calls=0;
 // Deliberately a deterministic test MAC; production OpenSSL/mbedTLS and
 // independent Python full-HMAC equality have separate cross-codec tests.
 auto mac=[&](const std::uint8_t*p,unsigned n,std::uint8_t*out){++calls;for(unsigned j=0;j<32;++j){out[j]=j;for(unsigned i=j;i<n;i+=32)out[j]^=p[i];}return true;};
 check(parts.prepare(r,7,8,12,8,UINT32_MAX,UINT32_MAX,5000000,mac,6));check(calls==3&&parts.parts()==3&&parts.part_index()==0&&parts.size()==250);
 std::array<std::uint8_t,32> proof{};std::memcpy(proof.data(),parts.data()+218,32);
 check(!parts.prepare(r,7,9,0,0,0,0,0,mac,6)&&calls==3);
 r.boost_control.values[1]=90; // An updated live sample cannot change parts.
 check(!parts.submitted()&&parts.part_index()==1&&parts.size()==232&&parts.pending());check(same(parts.data()+24,proof.data(),32)&&parts.data()[20]==6);
 check(!parts.submitted()&&parts.part_index()==2&&parts.size()==144&&parts.pending());check(same(parts.data()+24,proof.data(),32)&&parts.data()[5]==EngineBoost&&parts.data()[20]==6);
 float demand;const auto bits=read32(parts.data()+60);std::memcpy(&demand,&bits,4);check(demand==40);
 check(parts.data()[111]==0&&parts.data()[22]==0&&parts.data()[23]==0);
 check(!parts.expired(5250000)&&parts.expired(5250001)&&parts.expired(4999999));
 check(parts.submitted()&&!parts.pending()&&!parts.data()&&!parts.size()&&parts.prepared_us()==5000000&&parts.sequence()==8);check(!parts.submitted());
 for(unsigned failed_call=1;failed_call<=3;++failed_call){
  unsigned count=0;check(!parts.prepare(r,7,10,0,0,0,UINT32_MAX,0,[&](auto,unsigned,auto out){std::memset(out,0,32);return ++count!=failed_call;},6));check(!parts.pending()&&!parts.data()&&!parts.size());
  check(parts.prepare(r,7,11,0,0,0,UINT32_MAX,0,mac,6));parts.cancel();check(!parts.pending()&&parts.part_index()==0);
 }
 check(!parts.prepare(r,7,12,0,0,0,UINT32_MAX,0,mac,4));check(!parts.prepare(r,7,12,0,0,0,UINT32_MAX,0,mac,5));
 for(unsigned stage=0;stage<3;++stage){check(parts.prepare(r,7,13,0,0,0,UINT32_MAX,UINT64_MAX-10,mac,6));for(unsigned n=0;n<stage;++n)check(!parts.submitted());check(!parts.expired(UINT64_MAX)&&parts.expired(0));parts.cancel();check(!parts.pending());}
}
static void context_and_faults(){
 auto r=observation();check(engine_schema_supports(6,r));for(unsigned schema=1;schema<6;++schema)check(!engine_schema_supports(schema,r));
 r.timing_fault=r.last_timing_fault=18;check(engine_schema_supports(6,r));r.timing_fault=19;check(!engine_schema_supports(6,r));
 r=observation(230);check(r.boost_control.inhibit_engine&&r.controller_faults&engine::Overboost&&engine_schema_supports(6,r));
 for(unsigned field=0;field<7;++field){auto bad=r;switch(field){case 0:bad.flags&=~engine::FuelCut;break;case 1:bad.flags&=~engine::SparkCut;break;case 2:bad.flags|=engine::Pump;break;case 3:bad.flags|=engine::ProposedActive;break;case 4:bad.proposals[engine::PulseMs]=1;break;case 5:bad.controller_faults=0;break;case 6:bad.state=3;break;}check(!engine_schema_supports(6,bad));}
 r=observation();r.boost_control.values[1]=1000;r.boost_control.values[5]=-500;check(engine_schema_supports(6,r));r.boost_control.values[1]=-1000;check(engine_schema_supports(6,r));
 r.boost_control.values[0]=101;check(!engine_schema_supports(6,r));
 r=observation();r.boost_control=boost::record(boost::Output{},boost::Config{});check(!engine_schema_supports(6,r));r.input_valid&=~(1U<<engine::MapKpa);check(engine_schema_supports(6,r));r.inputs[engine::MapKpa]=110;r.input_valid|=1U<<engine::MapKpa;check(engine_schema_supports(6,r));
 r.inputs[engine::MapKpa]=400;r.boost_control=observation().boost_control;check(engine_schema_supports(6,r));r.inputs[engine::MapKpa]=401;check(!engine_schema_supports(6,r));
}
static_assert(sizeof(EnginePair)<=912,"Per-peer immutable observation RAM budget");
int main(){multipart();context_and_faults();std::cout<<"engine_radio_boost_checks "<<checks<<"\n";}
