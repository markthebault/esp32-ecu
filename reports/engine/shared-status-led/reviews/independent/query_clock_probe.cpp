#include "ecu/status_led.hpp"
#include <cstdio>
int main(){
 namespace sl=ecu::status_led;namespace si=ecu::switch_input;
 sl::Acquisition a;std::uint64_t now=100000;
 for(unsigned n=0;n<7;++n){
  const auto op=a.next(sl::Pattern::Normal,now,now);
  if(!op)return 1;
  si::Reply r;r.result=si::Result::Ok;r.size=op.read_size;
  for(unsigned k=0;k<sl::configuration.size();++k)r.data[k]=sl::configuration[k];
  r.data[9]=r.data[10]=a.snapshot(now).written_rgb;r.data[11]=0;
  if(!a.complete(op.token,r,now,now+100))return 2;
  const auto s=a.snapshot(now+100);
  if(s.ready){const auto q=a.snapshot(s.completed_us-1);
   std::printf("{\"observed_us\":%llu,\"completed_us\":%llu,\"query_us\":%llu,\"ready\":%s,\"fresh\":%s}\n",static_cast<unsigned long long>(q.observed_us),static_cast<unsigned long long>(q.completed_us),static_cast<unsigned long long>(s.completed_us-1),q.ready?"true":"false",q.fresh?"true":"false");return 0;}
  now+=5000;
 }
 return 3;
}
