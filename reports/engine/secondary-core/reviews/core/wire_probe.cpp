#include "ecu/tuning_layout.hpp"
#include <cstdio>
int main(){
 for(unsigned strategy=0;strategy<3;++strategy)for(unsigned source=0;source<3;++source)
 for(unsigned afr=0;afr<3;++afr)for(unsigned ae=0;ae<4;++ae){
  ecu::engine::Tune t;t.revision=42;t.strategy=ecu::engine::Strategy(strategy);t.cylinder_trims_enabled=strategy==1;
  t.load_model.fuel_source=t.load_model.spark_source=ecu::load::Source(source);
  t.load_model.ve_axis=t.load_model.spark_axis=t.load_model.lambda_axis=t.load_model.trim_axis=ecu::load::Axis(source);
  t.load_model.afr=ecu::load::Afr(afr);t.transient_enrichment.mode=ecu::transient::Mode(ae);
  t.load_model.aux_role=source==2?ecu::load::AuxRole::Emap:ecu::load::AuxRole::PostcatMonitor;
  for(auto*m:{&t.ve,&t.spark,&t.lambda})for(unsigned n=0;n<16;++n)m->load[n]=source==0?10+n*6.f:source==1?n*100.f/15:10+n*30.f;
  for(auto&m:t.cylinder_fuel)for(unsigned n=0;n<6;++n)m.load[n]=source==0?10+n*20.f:source==1?n*20.f:10+n*90.f;
  ecu::tuning::Page page;ecu::tuning::encode_page(t,42,page);
  ecu::engine::Tune restored;if(!ecu::tuning::decode_page(page,42,restored))return 2;
  ecu::tuning::Page encoded;ecu::tuning::encode_page(restored,42,encoded);if(page!=encoded)return 3;
  if(std::fwrite(page.data(),1,page.size(),stdout)!=page.size())return 4;
 }
}
