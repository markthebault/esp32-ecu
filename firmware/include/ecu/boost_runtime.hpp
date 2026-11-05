#pragma once
#include "ecu/boost_control.hpp"
#include <cfloat>

namespace ecu::boost {
inline constexpr const char* value_names[]={"duty_pct","demand_pct","target_kpa","feedforward_pct","error_kpa","p_term","i_term","d_term"};
inline constexpr const char* value_labels[]={"Duty","Demand","Target","Feedforward","Error","P","I","D"};
inline constexpr const char* value_units[]={"%","%","kPa","%","kPa","%","%","%"};
struct Record {
 std::array<std::uint64_t,2> counters{}; // PID updates, overboost events.
 std::array<float,8> values{NAN,NAN,NAN,NAN,NAN,NAN,NAN,NAN};
 std::uint32_t flags=0;
 std::uint8_t reason=0,mode=0;
 bool available=false,pressure_enabled=false,inhibit_engine=false;
};
static_assert(sizeof(Record)<=64,"Boost observation RAM budget");
inline Record record(const Output&o,const Config&c,bool available=true){
 Record r;r.available=available;r.pressure_enabled=c.pressure_enabled;r.mode=static_cast<std::uint8_t>(c.mode);
 if(!available)return r;
 r.counters={o.pid_updates,o.overboost_events};r.flags=o.flags;r.reason=static_cast<std::uint8_t>(o.reason);r.inhibit_engine=o.inhibit_engine;
 const double values[]={o.duty_pct,o.demand_pct,o.target_kpa,o.feedforward_pct,o.error_kpa,o.p_term,o.i_term,o.d_term};
 for(unsigned n=0;n<8;++n)r.values[n]=std::isfinite(values[n])&&std::abs(values[n])<=FLT_MAX?static_cast<float>(values[n]):NAN;
 return r;
}
inline bool valid_record(const Record&r,bool present=true){
 if(r.flags>2047||r.reason>16||r.mode>2||(!present&&(r.available||r.pressure_enabled||r.mode)))return false;
 if(r.mode&&!r.pressure_enabled)return false;
 for(auto v:r.values)if(std::isinf(v)||(!r.available&&std::isfinite(v)))return false;
 if(!r.available)return !r.flags&&!r.reason&&!r.inhibit_engine&&!r.counters[0]&&!r.counters[1];
 if(!bounded(r.values[0],0,100)||!std::isfinite(r.values[1])||!std::isfinite(r.values[5])||!std::isfinite(r.values[6])||!std::isfinite(r.values[7]))return false;
 if((std::isfinite(r.values[2])&&!bounded(r.values[2],50,400))||(std::isfinite(r.values[3])&&!bounded(r.values[3],0,100))||(std::isfinite(r.values[4])&&!bounded(r.values[4],-400,400)))return false;
 if(r.inhibit_engine&&(r.values[0]!=0||(r.flags&ValveAllowed)))return false;
 if(bool(r.flags&Enabled)!=r.pressure_enabled)return false;
 return true;
}
} // namespace ecu::boost
