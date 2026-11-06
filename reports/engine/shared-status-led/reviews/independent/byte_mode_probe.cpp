#include "ecu/status_led.hpp"
#include "ecu/switch_transport.hpp"
#include <cstdio>
namespace sl=ecu::status_led;namespace si=ecu::switch_input;
struct Device{
 std::uint64_t now=100000;std::array<std::uint8_t,11> r{0xff,0,0,0,0,0,0,0,0,0,0};
 si::Result prepare(){return si::Result::Ok;}
 si::Result read(std::uint8_t address,std::uint8_t*out,std::size_t n,int){now+=n==11?1200:400;for(unsigned i=0;i<n;++i){const auto at=address+((r[5]&0x20)?0:i);out[i]=at==9?std::uint8_t(r[10]&~r[0]):r[at];}return si::Result::Ok;}
 si::Result write(std::uint8_t address,const std::uint8_t*data,std::size_t n,int){now+=200;for(unsigned i=0;i<n;++i)r[address+((r[5]&0x20)?0:i)]=data[i];return si::Result::Ok;}
};
static sl::Snapshot tick(sl::Acquisition&a,Device&d){const auto start=d.now;const auto op=a.next(sl::Pattern::Off,start,start);if(op){const auto x=si::execute(op,d,[&](){return d.now;});a.complete(op.token,x.reply,x.started_us,x.ended_us);}const auto s=a.snapshot(d.now);d.now=std::max(d.now,start+5000);return s;}
int main(){sl::Acquisition a;Device d;sl::Snapshot s;for(unsigned n=0;n<20&&!s.ready;++n)s=tick(a,d);
 if(!s.ready)return 2;
 d.r[5]=0x20;d.now+=sl::verify_us;s=tick(a,d);
 std::printf("{\"physical_IOCON\":%u,\"driver_expected_IOCON\":%u,\"ready\":%s,\"configured\":%s,\"fresh\":%s,\"fault\":\"%s\",\"verifications\":%llu}\n",d.r[5],sl::configuration[5],s.ready?"true":"false",s.configured?"true":"false",s.fresh?"true":"false",si::fault_name(s.fault),static_cast<unsigned long long>(s.verifications));}
