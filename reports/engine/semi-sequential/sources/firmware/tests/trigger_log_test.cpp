#include "ecu/trigger_log.hpp"
#include <cassert>
#include <iostream>
using namespace ecu::trigger_log;
Record edge(std::uint64_t time,bool cam=false,bool high=true){return {time,time+2,static_cast<std::uint32_t>(time*80),3,cam,high,true};}
int main(){
 Capture capture;assert(capture.header().state==State::Idle);
 assert(!capture.start(15,1000,0)&&!capture.start(513,1000,0)&&!capture.start(16,49,0)&&!capture.start(16,5001,0));
 assert(capture.start(16,1000,1000));const auto id=capture.header().frame_id;
 assert(!capture.start(16,1000,1001)&&!capture.stop(id+1,1001));
 capture.append(edge(999));assert(capture.header().prearm_ignored==1&&capture.header().count==0);
 auto invalid=edge(1001);invalid.timebase_valid=false;capture.append(invalid);assert(capture.header().invalid_timebase_ignored==1&&capture.header().count==0);
 // Preserve callback order even when separate capture channels deliver older
 // latched timestamps later. Do not invent a monotonically sorted waveform.
 capture.append(edge(1100,true,false));auto older=edge(1050,false,true);older.callback_us=1103;capture.append(older);
 for(unsigned i=2;i<16;++i)capture.append(edge(1200+i,i%2,i%3));
 assert(capture.header().state==State::Full&&capture.header().count==16);
 Record record;assert(capture.read(id,1,record)&&record.captured_us==1050);
 capture.append(edge(2000));assert(capture.header().count==16);assert(capture.stop(id,2001));
 assert(capture.start(512,50,2002));assert(!capture.read(id,0,record));
 capture.append(edge(2100));capture.expire(52002);assert(capture.header().state==State::Timeout&&capture.header().count==1);
 const auto timeout_id=capture.header().frame_id;assert(capture.stop(timeout_id,52003));
 assert(capture.start(16,100,100000));capture.expire(99999);assert(capture.header().state==State::Clock);
 assert(capture.start(512,5000,200000));
 for(unsigned i=0;i<513;++i)capture.append(edge(200000+i));
 assert(capture.header().count==512&&capture.header().state==State::Full);
 assert(!capture.start(16,100,UINT64_MAX-1));
 Capture partial;assert(partial.start(16,100,1000));partial.append(edge(1010));
 const auto partial_id=partial.header().frame_id;assert(partial.stop(partial_id,1020));partial.append(edge(1030));
 assert(partial.header().state==State::Stopped&&partial.header().count==1);
 assert(partial.read(partial_id,0,record)&&record.captured_us==1010);
 std::cout<<"Finite trigger frame, edge ordering, stale-frame, timeout, invalid timebase and capacity tests passed\n";
}
