#include "ecu/flex_fuel.hpp"
#include <iostream>
int main(){
 ecu::flex::Capture c;
 c.edge(0,true);
 for(unsigned n=1;n<=8;++n){c.edge(n*20000-3000,false);c.edge(n*20000,true);}
 auto good=c.observe(160000);
 c.edge(177000,false);
 auto stale=c.observe(411000);
 ecu::flex::CorrectionConfig cfg;cfg.enabled=true;
 auto e=ecu::flex::evaluate(cfg,c.config(),stale,411000);
 std::cout<<"good="<<good.valid<<" stale="<<stale.valid<<" reason="<<ecu::flex::reason_name(stale.reason)<<" age_ms="<<stale.age_ms<<" pending="<<stale.pending_fault<<" correction_valid="<<e.valid<<" correction_reason="<<ecu::flex::reason_name(e.reason)<<"\n";
}
