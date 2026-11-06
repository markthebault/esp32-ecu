#include "ecu/secondary_tables.hpp"
#include <iostream>
namespace s=ecu::secondary;
int main(){s::Controller c;s::Rule r;r.mode=s::Mode::Input;r.debounce_ms=20;s::Input i;i.map_kpa=40;i.map_qualified=true;i.tps_pct=20;
for(unsigned n=0;n<3;++n){const auto t=1000000+n*10000;i.switches[0]={t,s::InputSource::Synthetic,true,true};auto q=c.select(s::Kind::Spark,r,i,t,true);std::cout<<t<<" crank: ok="<<q.ok<<" qualified="<<q.observation.input_qualified<<'\n';}
i.map_qualified=false;i.switches[0]={1025000,s::InputSource::Synthetic,true,false};auto q=c.select(s::Kind::Spark,r,i,1025000,false);std::cout<<"1025000 first_run map+switch fault: ok="<<q.ok<<" reason="<<s::reason_name(q.observation.reason)<<" input_valid="<<q.observation.input_valid<<'\n';
i.map_qualified=true;i.switches[0]={1030000,s::InputSource::Synthetic,true,true};q=c.select(s::Kind::Spark,r,i,1030000,false);std::cout<<"1030000 recovered fresh sample: ok="<<q.ok<<" qualified="<<q.observation.input_qualified<<" active="<<q.observation.active<<" reason="<<s::reason_name(q.observation.reason)<<'\n';}
