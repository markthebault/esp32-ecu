#include "ecu/flex_capture_owner.hpp"
#include <cstdio>
int main(){
 namespace f=ecu::flex;f::CaptureConfig cal;cal.cycles=2;f::Capture capture(cal);f::CapturePort port;f::CaptureRequest r;r.calibration=cal;r.required=r.confirmed=true;r.tune_revision=r.sensor_revision=1;
 auto w=port.configure(r,1,true,true,true,250000,1000);if(!port.arm(w.version,1000))return 1;
 auto edge=[&](std::uint64_t t,bool high){if(port.push(t,t,high,true,0)!=f::Ingress::Result::Accepted)return false;f::IngressEdge e;if(!port.pop(port.version(),e))return false;capture.edge(e.captured_us,e.high,f::Source::TargetCapture);return true;};
 for(auto t:{2000ULL,9000ULL,12000ULL,19000ULL,22000ULL})if(!edge(t,t%10000==2000))return 2;
 f::Sample s{capture.observe(22000),cal,1};if(!s.observation.valid||!port.publish(port.version(),s,22000))return 3;const auto first=port.view(22000).ticket;
 if(!edge(29000,false)||!edge(32000,true))return 4;
 s.observation=capture.observe(32000);if(!port.publish(port.version(),s,32000))return 5;
 const auto second=port.view(32000).ticket;const bool old_before=port.can_dispatch(first,32000,false);
 auto rejected=s;rejected.observation.source=f::Source::Synthetic;if(port.publish(port.version(),rejected,32000))return 6;
 const bool current_after_failure=port.view(32000).current;const bool old_during=port.can_dispatch(second,32000,false);
 capture.restart();for(auto t:{39000ULL,42000ULL,49000ULL,52000ULL,59000ULL,62000ULL})if(!edge(t,t%10000==2000))return 7;
 s.observation=capture.observe(62000);if(!s.observation.valid||s.observation.fault_generation||!port.publish(port.version(),s,62000))return 8;
 const auto v=port.view(62000);const bool old_after=port.can_dispatch(first,62000,false)||port.can_dispatch(second,62000,false);const bool fresh=port.can_dispatch(v.ticket,62000,false);
 std::printf("{\"old_eligible_after_good_publication\":%s,\"view_current_after_failure\":%s,\"old_eligible_during_rejection\":%s,\"old_eligible_after_same_generation_recovery\":%s,\"new_eligible\":%s,\"fault_generation\":%llu,\"old_deadline_still_in_future\":%s}\n",old_before?"true":"false",current_after_failure?"true":"false",old_during?"true":"false",old_after?"true":"false",fresh?"true":"false",static_cast<unsigned long long>(s.observation.fault_generation),first.valid_until_us>62000?"true":"false");
}
