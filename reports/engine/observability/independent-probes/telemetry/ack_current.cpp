#include "ecu/engine_radio.hpp"
#include <cassert>
#include <cstdint>
#include <iostream>
int main(){
 using ecu::radio::wire::SentWindow;
 SentWindow<std::uint32_t> s;
 std::uint64_t t=1000000;
 for(auto seq:{UINT32_MAX-1,UINT32_MAX,0U,1U}){s.submitted(seq,t);assert(s.acknowledge(seq,t));assert(!s.acknowledge(seq,t+1));t+=100;}
 s.submitted(3,t);assert(!s.acknowledge(3,t+1000001));s.submitted(2,t+1000002);assert(s.acknowledge(2,t+1000002));
 s.submitted(4,t+2000000);assert(!s.acknowledge(4,t+1999999));assert(s.acknowledge(4,t+3000000));
 s.submitted(5,t+3000001);for(unsigned i=6;i<14;++i)s.submitted(i,t+3000002);
 assert(!s.acknowledge(5,t+3000002));assert(s.acknowledge(13,t+3000002));
 s.reset();assert(!s.acknowledge(13,t+3000003));s.submitted(0,t+4000000);assert(s.acknowledge(0,t+4000000));
 SentWindow<std::uint64_t> wide;const std::uint64_t big=UINT64_C(9007199254740993);
 wide.submitted(big,100);assert(!wide.acknowledge(big,1000101));assert(wide.acknowledge(big,1000100));
 wide.submitted(big+2,2000000);assert(!wide.acknowledge(big+1,2000000));assert(wide.acknowledge(big+2,2000000));
 assert(sizeof(ecu::engine::RuntimeSample)<=224);std::cout<<"ACK rollover, zero, expiry, future time, no rejected-ACK state advance, overwrite, reset and 64-bit exactness passed. RuntimeSample bytes="<<sizeof(ecu::engine::RuntimeSample)<<"\n";
}
