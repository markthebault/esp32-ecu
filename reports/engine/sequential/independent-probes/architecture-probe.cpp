#include "ecu/engine_phase.hpp"
#include "ecu/timing_executor.hpp"
#include <algorithm>
#include <iostream>
#include <vector>
using namespace ecu::engine;
struct Event {std::uint64_t delivered,captured;bool cam;};
void delayed_crank(bool after_lock){
 AngleConfig c;c.strategy=Strategy::Sequential;c.cam_sync_deg=180;PhaseDecoder p({120,2,8000},c);std::vector<Event> events;
 for(unsigned n=0;n<1200;++n)if(n%120<118){auto t=std::uint64_t(std::llround(1+n*62.5));events.push_back({t+((!after_lock||n>=720)?1000:0),t,false});}
 for(unsigned n=90;n<1200;n+=240){auto t=std::uint64_t(std::llround(1+n*62.5));events.push_back({t,t,true});}
 std::sort(events.begin(),events.end(),[](const auto&a,const auto&b){return a.delivered<b.delivered||(a.delivered==b.delivered&&a.cam<b.cam);});
 bool ever=false;for(const auto&e:events){if(e.cam)p.cam(e.captured);else p.edge(e.captured);ever|=p.phase_synced();p.tick(e.delivered);}
 std::cout<<"  \""<<(after_lock?"crank_lag_after_lock":"crank_lag_during_acquisition")<<"\": {\"ever_locked\": "<<(ever?"true":"false")<<", \"locked\": "<<(p.phase_synced()?"true":"false")<<", \"faulted\": "<<(p.faulted()?"true":"false")<<", \"accepted\": "<<p.accepted()<<", \"rejected\": "<<p.rejected()<<", \"reason\": \""<<PhaseDecoder::reason_name(p.reason())<<"\"},\n";
}
struct IO {unsigned mask=0;void all_low(){mask=0;}bool write(unsigned ch,bool high){if(high)mask|=1U<<ch;else mask&=~(1U<<ch);return true;}};
int main(){std::cout<<"{\n";delayed_crank(false);delayed_crank(true);
 using namespace ecu::timing;Executor x;IO io;Command c;c.angle.strategy=Strategy::Sequential;c.sequence=c.tune_revision=c.sensor_revision=1;c.command_us=c.sampled_us=1;x.progress(1,io);x.command(c,1,io);x.phase(true,3001,1,io);const auto alarm=x.next_alarm();x.dispatch(3001,io);x.phase(true,10000,3002,io);
 std::cout<<"  \"inactive_cam_guard\": {\"alarm\": "<<alarm<<", \"fault_after_expiry_and_renewal\": \""<<cause_name(x.stats().fault)<<"\"}\n}\n";
}
