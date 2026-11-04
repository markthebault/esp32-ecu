#pragma once
#include "ecu/switch_acquisition.hpp"

namespace ecu::switch_input {
struct Execution {Reply reply;std::uint64_t started_us=0,ended_us=0;};

// Backend: prepare(), read(reg,bytes,count,timeout_ms), write(...), returning
// Result. Clock uses the same monotonic microsecond epoch as the controller.
// One logical operation per call. GuardedRead consists of two synchronous
// transactions, with an independent trailing IODIR read to catch mid-read reset.
template<class Backend,class Clock>
Execution execute(const Request&op,Backend&backend,Clock clock){
 Execution out;out.reply.data.fill(0xa5);out.started_us=out.ended_us=clock();
 if(out.started_us<op.issued_us){out.reply.result=Result::ClockError;return out;}
 auto previous=out.started_us;
 auto remaining_ms=[&](){
  const auto now=clock();out.ended_us=now;
  if(now<previous||now<op.issued_us){out.reply.result=Result::ClockError;return 0;}
  previous=now;
  if(now-op.issued_us>budget_us){out.reply.result=Result::NoBudget;return 0;}
  const auto remaining=(budget_us-(now-op.issued_us))/1000;
  if(!remaining){out.reply.result=Result::NoBudget;return 0;}
  return static_cast<int>(remaining);
 };
 auto finish=[&](){
  const auto now=clock();out.ended_us=now;
  if(now<previous||now<op.issued_us)out.reply.result=Result::ClockError;
  else if(now-op.issued_us>budget_us)out.reply.result=Result::NoBudget;
  previous=now;
 };
 if(!op||op.write_size>op.data.size()||op.read_size>out.reply.data.size()||
    (op.write_size&&op.read_size)||(op.kind==Kind::GuardedRead&&(op.reg||op.read_size!=12))){
  out.reply.result=Result::BusError;return out;
 }
 if(!remaining_ms())return out;
 out.reply.result=backend.prepare();finish();
 if(out.reply.result!=Result::Ok)return out;
 const int timeout=remaining_ms();if(!timeout)return out;
 if(op.write_size){
  out.reply.result=backend.write(op.reg,op.data.data(),op.write_size,timeout);finish();
 }else if(op.kind==Kind::GuardedRead){
  out.reply.result=backend.read(0,out.reply.data.data(),11,timeout);finish();
  if(out.reply.result!=Result::Ok)return out;
  const int guard_timeout=remaining_ms();if(!guard_timeout)return out;
  out.reply.result=backend.read(0,&out.reply.data[11],1,guard_timeout);finish();
 }else{
  out.reply.result=backend.read(op.reg,out.reply.data.data(),op.read_size,timeout);finish();
 }
 if(out.reply.result==Result::Ok)out.reply.size=op.read_size;
 return out;
}
} // namespace ecu::switch_input
