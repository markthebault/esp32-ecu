#pragma once
#include "ecu/realtime.hpp"
#include <algorithm>
#include <cstdint>
#include <limits>
namespace ecu::idle {
enum class PwmCause:std::uint8_t {None,Disabled,Configuration,EngineFault,CommandExpired,LateInterrupt,InvalidCommand,Clock,OutputFault};
inline const char* pwm_cause_name(PwmCause c){switch(c){case PwmCause::None:return "none";case PwmCause::Disabled:return "disabled";case PwmCause::Configuration:return "configuration";case PwmCause::EngineFault:return "engine_fault";case PwmCause::CommandExpired:return "command_expired";case PwmCause::LateInterrupt:return "late_interrupt";case PwmCause::InvalidCommand:return "invalid_command";case PwmCause::Clock:return "clock_reversed";default:return "output_fault";}}
struct PwmCommand {
 std::uint64_t sequence=0,command_us=0,sampled_us=0;
 std::uint32_t tune_revision=0,sensor_revision=0,period_us=10000,high_us=0;
 bool enabled=false,supervised_stop=false;
};
struct PwmStats {
 std::uint64_t accepted=0,rejected=0,cycles=0,rises=0,falls=0,faults=0,cuts=0,recoveries=0,max_lateness_us=0;
 std::uint64_t sequence=0,observed_us=0;
 std::uint32_t tune_revision=0,sensor_revision=0,period_us=0,high_us=0;
 bool active=false,high=false;
 PwmCause fault=PwmCause::None,last_cause=PwmCause::Disabled;
};
// Fixed storage and integer-only dispatch, usable inside the common GPTimer
// owner. A separate applied-idle observation avoids truncating the eight-bit
// injector/coil masks. IO is a dedicated one-pin sink; no GPIO call lives here.
class PwmExecutor {
 static constexpr std::uint64_t never=UINT64_MAX,maximum_age_us=20000,maximum_lateness_us=25;
 PwmCommand pending_{};PwmStats stats_;
 std::uint64_t deadline_=never,fall_=never,cycle_=never,last_=0,quiet_since_=0,last_zero_=0;
 bool seen_=false,quiet_=false;
 template<class IO>ECU_ISR_CODE void level(bool high,std::uint64_t now,IO&io){
  if(stats_.high==high)return;
  if(!io.write(high)){
   io.all_low();stats_.high=stats_.active=false;deadline_=fall_=cycle_=never;
   if(stats_.fault==PwmCause::None){stats_.fault=PwmCause::OutputFault;++stats_.faults;}stats_.last_cause=PwmCause::OutputFault;return;
  }
  stats_.high=high;if(high)++stats_.rises;else ++stats_.falls;stats_.observed_us=now;
 }
 template<class IO>ECU_ISR_CODE void boundary(std::uint64_t now,IO&io){
  stats_.period_us=pending_.period_us;stats_.high_us=pending_.high_us;++stats_.cycles;
  cycle_=now+stats_.period_us;
  fall_=stats_.high_us&&stats_.high_us<stats_.period_us?now+stats_.high_us:never;
  level(stats_.high_us>0,now,io);
 }
public:
 ECU_ISR_CODE const PwmStats& stats()const{return stats_;}
 ECU_ISR_CODE const PwmCommand& command()const{return pending_;}
 ECU_ISR_CODE std::uint64_t next_alarm()const{return stats_.active?std::min(deadline_,std::min(fall_,cycle_)):never;}
 template<class IO>ECU_ISR_CODE void stop(std::uint64_t now,PwmCause cause,IO&io){
  const bool was=stats_.active||stats_.high;io.all_low();if(stats_.high)++stats_.falls;
  stats_.active=stats_.high=false;stats_.high_us=0;stats_.observed_us=now;deadline_=fall_=cycle_=never;quiet_=false;
  if(was){++stats_.cuts;}stats_.last_cause=cause;
 }
 template<class IO>ECU_ISR_CODE void trip(std::uint64_t now,PwmCause cause,IO&io){
  if(stats_.fault==PwmCause::None){stats_.fault=cause;++stats_.faults;}stop(now,cause,io);
 }
 template<class IO>ECU_ISR_CODE void dispatch(std::uint64_t now,IO&io){
  if(seen_&&now<last_){trip(now,PwmCause::Clock,io);last_=now;return;}seen_=true;last_=now;
  if(!stats_.active)return;
  if(now>=deadline_){trip(now,PwmCause::CommandExpired,io);return;}
  const auto due=std::min(fall_,cycle_);if(now<due)return;
  stats_.max_lateness_us=std::max(stats_.max_lateness_us,now-due);
  if(now-due>maximum_lateness_us){trip(now,PwmCause::LateInterrupt,io);return;}
  if(fall_<=cycle_){fall_=never;level(false,now,io);}
  else boundary(cycle_,io); // Carry the scheduled phase, do not accumulate lateness.
 }
 template<class IO>bool submit(const PwmCommand&c,std::uint64_t now,IO&io){
  // Expiry is evaluated before a new heartbeat can rescue an old command.
  dispatch(now,io);
  const bool valid=c.sequence&&c.sequence>stats_.sequence&&c.tune_revision&&c.sensor_revision&&c.command_us<=now&&c.sampled_us<=now&&
   now-c.command_us<maximum_age_us&&now-c.sampled_us<maximum_age_us&&c.period_us>=2500&&c.period_us<=50000&&c.high_us<=c.period_us&&now<=UINT64_MAX-50000;
  if(!valid){++stats_.rejected;trip(now,PwmCause::InvalidCommand,io);return false;}
  pending_=c;stats_.sequence=c.sequence;stats_.tune_revision=c.tune_revision;stats_.sensor_revision=c.sensor_revision;++stats_.accepted;
  if(!c.enabled||!c.high_us){
   const bool quiet=quiet_;const auto since=quiet_since_;stop(now,PwmCause::Disabled,io);quiet_=quiet;quiet_since_=since;
   // Only explicit fresh zero commands permit fault recovery. Ordinary live
   // requests never clear a timeout/fault and resume a stale pulse train.
   if(stats_.fault!=PwmCause::None&&c.supervised_stop){
    if(!quiet_||now<last_zero_||now-last_zero_>=maximum_age_us){quiet_=false;}last_zero_=now;
    if(!quiet_){quiet_=true;quiet_since_=now;}
    else if(now-quiet_since_>=20000){stats_.fault=PwmCause::None;++stats_.recoveries;quiet_=false;}
   }else quiet_=false;
   return true;
  }
  quiet_=false;
  if(stats_.fault!=PwmCause::None){++stats_.rejected;return false;}
  deadline_=std::min(c.command_us,c.sampled_us)+maximum_age_us;
  if(!stats_.active){stats_.active=true;boundary(now,io);}
  return stats_.fault==PwmCause::None;
 }
 template<class IO>void configuration(std::uint64_t now,IO&io){stop(now,PwmCause::Configuration,io);stats_.fault=PwmCause::None;pending_={};}
};
} // namespace ecu::idle
