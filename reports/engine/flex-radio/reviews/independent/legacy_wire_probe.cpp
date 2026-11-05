#include "ecu/engine_radio.hpp"
#include <cstdio>
int main(){
 namespace w=ecu::radio::wire;unsigned vectors=0;
 for(unsigned schema=1;schema<=4;++schema){const unsigned count=schema==4?225:64;
  for(unsigned n=0;n<count;++n){ecu::engine::RuntimeSample r;r.sequence=100+n;r.source=n%2?ecu::engine::DataSource::Target:ecu::engine::DataSource::Synthetic;r.tune_revision=7;r.sensor_revision=9;r.phase_epoch=11;r.worker_epoch=13;r.worker_sequence=50+n;r.worker_tune_revision=7;r.worker_sensor_revision=9;
   r.flags=ecu::engine::Present|ecu::engine::StorageOk|ecu::engine::InputsFresh|ecu::engine::InputsQualified|ecu::engine::Submitted|(n%2?ecu::engine::FuelCut:ecu::engine::ProposedActive);r.state=n%2?5:2;r.strategy=n%(schema==1?2:3);r.input_valid=static_cast<unsigned char>(n*37);r.phase_reason=n%10;r.board_flags=n%16;r.cam_error_deg=float(n)/100;r.controller_faults=n%2?std::uint32_t(ecu::engine::BadSensor):0U;r.phase_losses=n*3;r.cam_rejected=n*5;r.virtual_high_mask=n%16;r.physical_command_mask=0;
   const float inputs[]={2000,50,10,85,25,1,14,5};for(unsigned i=0;i<8;++i)r.inputs[i]=inputs[i];for(unsigned i=0;i<14;++i)r.proposals[i]=i==2?1:float(i+n%17)/10;
   if(schema==4){const unsigned fs=n%3,ss=(n/3)%3,fm=(n/9)%5,sm=n/45;
    r.secondary_fuel.available=r.secondary_spark.available=true;r.secondary_fuel.evaluated=r.secondary_spark.evaluated=true;r.secondary_fuel.mode=static_cast<ecu::secondary::Mode>(fm);r.secondary_spark.mode=static_cast<ecu::secondary::Mode>(sm);r.secondary_fuel.source=static_cast<ecu::load::Source>(fs);r.secondary_spark.source=static_cast<ecu::load::Source>(ss);r.secondary_fuel.active=fm&&bool(n%2);r.secondary_spark.active=sm&&bool(n%3);}
   constexpr std::uint32_t ages[]={0,12,1001,UINT32_MAX};unsigned char packet[250]{};const bool ok=w::engine_body(packet,r,0x12345678,1000+n,ages[n%4],ages[(n+1)%4],ages[(n+2)%4],5000000+5000*n,schema);
   unsigned char prefix[8]{};w::u16(prefix,schema);w::u16(prefix+2,n);w::u16(prefix+4,ok?w::engine_frame_size(schema):0);prefix[6]=ok;
   if(std::fwrite(prefix,1,sizeof prefix,stdout)!=sizeof prefix)return 1;
   if(ok&&std::fwrite(packet,1,w::engine_frame_size(schema),stdout)!=w::engine_frame_size(schema))return 2;
   ++vectors;
  }
  ecu::engine::RuntimeSample blocked;blocked.sequence=1;blocked.flags=ecu::engine::Present;blocked.source=ecu::engine::DataSource::Synthetic;blocked.flex_fuel.flags=ecu::flex::Required|ecu::flex::CorrectionsEnabled;unsigned char p[250]{};
  if(w::engine_schema_supports(schema,blocked)||w::engine_body(p,blocked,1,1,0,0,0,1,schema))return 3;
 }
 return vectors==417?0:4;
}
