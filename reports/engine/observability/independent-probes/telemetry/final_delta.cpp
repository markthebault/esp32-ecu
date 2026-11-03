#include "ecu/engine_radio.hpp"
#include <cassert>
#include <iostream>
int main(){
 using namespace ecu::radio::wire;
 static_assert(capability_size==76&&capability_reply_size==108&&engine_size==232&&engine_ack_size==56);
 std::uint8_t query[capability_size]{};header(query,Capabilities,capability_size);query[16]=1;
 PeerCapabilities caps;assert(!caps.request(query,sizeof(query),0));assert(!caps.pending());assert(caps.request(query,sizeof(query),123));
 std::uint8_t boot[16]{},reply[capability_reply_size]{};boot[0]=42;
 caps.reply(reply,123,boot,UINT64_C(9007199254740993),5000000);
 assert(valid(reply,sizeof(reply),CapabilitiesReply,108));assert(read32(reply+8)==123&&read32(reply+12)==0&&reply[16]==1);
 assert(read32(reply+32)==0&&read32(reply+36)==0&&read32(reply+40)==0&&reply[44]==42);
 assert(read64(reply+60)==UINT64_C(9007199254740993)&&read64(reply+68)==5000000);
 ecu::engine::RuntimeSample sample;sample.flags=ecu::engine::Present;sample.sequence=7;sample.source=ecu::engine::DataSource::Target;
 std::uint8_t packet[engine_size]{};assert(!engine_body(packet,sample,0,1,0,0,0,100));
 assert(engine_body(packet,sample,123,1,0,0,0,100));assert(valid(packet,sizeof(packet),EngineTelemetry,232));
 assert(read32(packet+8)==123&&read64(packet+12)==1&&read64(packet+40)==7&&read64(packet+92)==100);
 std::cout<<"Final packet-size, reply-offset and zero-current-session helper guards passed\n";
}
