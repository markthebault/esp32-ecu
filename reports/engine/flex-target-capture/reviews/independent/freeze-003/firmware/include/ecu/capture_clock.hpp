#pragma once
#include "ecu/realtime.hpp"
#include <cstdint>
#include <limits>

namespace ecu::timing {
// Capture and GPTimer must use the same APB clock. Startup software sync is
// bracketed by GPTimer reads while capture channels and outputs are disabled.
// Each channel resolves independently, so reversed callback delivery order
// does not corrupt counter wrap reconstruction.
class CaptureClock {
public:
 enum class Error : std::uint8_t {None,Uninitialized,Frequency,WideBracket,BeforeEpoch,Future,TooOld};
 struct Result {std::uint64_t time_us=0;std::uint32_t age_us=0;Error error=Error::Uninitialized;};
 bool sync(std::uint32_t capture_hz,std::uint64_t before,std::uint64_t after){
  ready_=false;
  if(!capture_hz||capture_hz%1000000||capture_hz/1000000>80){error_=Error::Frequency;return false;}
  if(after<before||after-before>10){error_=Error::WideBracket;return false;}
  ticks_per_us_=capture_hz/1000000;
  lower_epoch_=before;
  epoch_=before+(after-before)/2;
  uncertainty_=static_cast<std::uint32_t>((after-before+1)/2+1);
  error_=Error::None;ready_=true;return true;
 }
 ECU_ISR_CODE Result map(std::uint32_t captured,std::uint64_t observed)const{
  Result r;
  if(!ready_){r.error=error_;return r;}
  if(observed<epoch_){r.error=Error::BeforeEpoch;return r;}
  const std::uint32_t expected=static_cast<std::uint32_t>(observed-epoch_)*ticks_per_us_;
  const std::uint32_t ahead=captured-expected;
  if(ahead<=uncertainty_*ticks_per_us_){r.time_us=observed;r.error=Error::None;return r;}
  const std::uint32_t behind=expected-captured;
  if(behind>5000U*ticks_per_us_){r.error=ahead<0x80000000U?Error::Future:Error::TooOld;return r;}
  // A32-bit division by a small integer; no floating point or64-bit divide in ISR.
  r.age_us=(behind+ticks_per_us_-1)/ticks_per_us_;
  if(r.age_us>observed){r.error=Error::BeforeEpoch;return r;}
  r.time_us=observed-r.age_us;r.error=Error::None;return r;
 }
 // Pulse widths need a fixed epoch, rather than the crank mapping's
 // uncertainty-sized per-callback clamp. The earlier bracket endpoint is a
 // conservative absolute offset shared by ALL edges. Widths then depend only
 // on captured ticks, with <1us integer quantization. No timer is resynced.
 ECU_ISR_CODE Result map_interval(std::uint32_t captured,std::uint64_t observed)const{
  Result r;
  if(!ready_){r.error=error_;return r;}
  if(observed<lower_epoch_){r.error=Error::BeforeEpoch;return r;}
  const std::uint32_t expected=static_cast<std::uint32_t>(observed-lower_epoch_)*ticks_per_us_;
  const std::uint32_t ahead=captured-expected;
  // GPtime is expressed in whole us. A fractional captured tick in the same
  // us floors to observed; uncertainty never widens this sub-us allowance.
  if(ahead<ticks_per_us_){r.time_us=observed;r.error=Error::None;return r;}
  const std::uint32_t behind=expected-captured;
  if(behind>5000U*ticks_per_us_){r.error=ahead<0x80000000U?Error::Future:Error::TooOld;return r;}
  r.age_us=(behind+ticks_per_us_-1)/ticks_per_us_;
  if(r.age_us>observed){r.error=Error::BeforeEpoch;return r;}
  r.time_us=observed-r.age_us;r.error=Error::None;return r;
 }
 bool ready()const{return ready_;}
 std::uint64_t epoch_us()const{return epoch_;}
 std::uint32_t uncertainty_us()const{return uncertainty_;}
 Error error()const{return error_;}
private:
 std::uint64_t epoch_=0,lower_epoch_=0;
 std::uint32_t ticks_per_us_=0,uncertainty_=0;
 bool ready_=false;Error error_=Error::Uninitialized;
};
}
