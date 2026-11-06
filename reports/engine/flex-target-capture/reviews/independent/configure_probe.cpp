#include "ecu/flex_capture_owner.hpp"
#include <cstdio>
int main(){
 ecu::flex::CapturePort p;ecu::flex::CaptureRequest r;r.required=r.confirmed=true;r.tune_revision=1;r.sensor_revision=1;r.calibration.low_hz=1;
 const auto a=p.configure(r,1,true,true,false,0,1000);
 const auto b=p.configure(r,1,true,true,false,0,2000);
 const auto c=p.configure(r,1,true,true,false,0,3000);
 std::printf("{\"contexts\":[%llu,%llu,%llu],\"generation\":[%llu,%llu,%llu],\"same_immutable_request\":true,\"calibration_valid\":false,\"binding\":%s}\n",static_cast<unsigned long long>(a.version.context),static_cast<unsigned long long>(b.version.context),static_cast<unsigned long long>(c.version.context),static_cast<unsigned long long>(a.version.generation),static_cast<unsigned long long>(b.version.generation),static_cast<unsigned long long>(c.version.generation),c.binding?"true":"false");
}
