#include "ecu/flex_capture_owner.hpp"
#include <cstdio>
int main(){
 namespace f=ecu::flex;f::CaptureConfig cal;cal.cycles=2;f::Capture capture(cal);f::CapturePort port;f::CaptureRequest request;request.calibration=cal;request.required=request.confirmed=true;request.tune_revision=request.sensor_revision=1;
 auto w=port.configure(request,1,true,true,true,250000,1000);if(!port.arm(w.version,1000))return 1;
 auto edge=[&](std::uint64_t time,bool high){if(port.push(time,time,high,true,0)!=f::Ingress::Result::Accepted)return false;f::IngressEdge e;if(!port.pop(port.version(),e))return false;capture.edge(e.captured_us,e.high,f::Source::TargetCapture);return true;};
 for(auto time:{2000ULL,9000ULL,12000ULL,19000ULL,22000ULL})if(!edge(time,time%10000==2000))return 2;
 f::Sample sample{capture.observe(22000),cal,1};if(!sample.observation.valid||!port.publish(port.version(),sample,22000))return 3;
 const auto old=port.view(22000);const auto version=port.version();if(!port.can_issue(old.ticket,22000,false))return 4;
 //900us LOW is rejected only by floating-point Capture. Integer ingress
 // accepts its alternating, well-spaced edges and retains its exact version.
 if(!edge(31100,false)||!edge(32000,true))return 5;
 sample.observation=capture.observe(32000);if(sample.observation.valid||!sample.observation.pending_fault||sample.observation.reason!=f::Reason::PulseWidth)return 6;
 if(!port.publish(port.version(),sample,32000))return 7;
 const auto bad=port.view(32000);
 const bool same_version=f::same(version,port.version());const bool during=port.can_dispatch(old.ticket,32000,false);
 // Model a completed invalid control observation before this exact ACK.
 if(!port.acknowledge(bad,32000)||!capture.acknowledge(sample.observation.fault_generation))return 8;
 for(auto time:{39000ULL,42000ULL,49000ULL,52000ULL})if(!edge(time,time%10000==2000))return 9;
 sample.observation=capture.observe(52000);if(!sample.observation.valid||!port.publish(port.version(),sample,52000))return 10;
 const bool after=port.can_dispatch(old.ticket,52000,false),fresh=port.can_dispatch(port.view(52000).ticket,52000,false);
 std::printf("{\"same_ingress_version\":%s,\"old_allowed_during_Capture_fault\":%s,\"old_allowed_after_raw_recovery\":%s,\"new_allowed_after_recovery\":%s,\"Capture_fault_generation\":%llu}\n",same_version?"true":"false",during?"true":"false",after?"true":"false",fresh?"true":"false",static_cast<unsigned long long>(sample.observation.fault_generation));
}
