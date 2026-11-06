// Actual source-level sender functions with the frozen native API model.
// The infinite RTOS task, ESP32 image, RF, GPIO and I2C do not execute.
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wreturn-type"
#define main unused_parent_sender_main
#include "radio_service_test.cpp"
#undef main
#pragma GCC diagnostic pop
static void advance(std::int64_t t){fake_radio_now=t;fake_now=21000+t-20000000;}
static void sensor_ack(std::uint32_t sequence){
 r::streams[0].sensor_sent.submitted(sequence,r::now());std::vector<std::uint8_t> p(52);w::header(p.data(),w::Ack,52);w::u32(p.data()+8,r::session_id);w::u32(p.data()+12,sequence);check(r::hmac(r::saved.peers[0].key,p.data(),20,p.data()+20));input(p);
}
static void flex_off_live(ecu::engine::RuntimeSample good){good.flex_fuel={};good.sampled_us=good.control_us=fake_now;publish(good);check(!r::live.fault);}
int main(){
 r::start();r::radio_ok=r::storage_ok=true;r::session_id=0x12345678;esp_fill_random(r::engine_nonce,16);esp_wifi_get_mac(0,r::own);
 r::saved=r::Store{};r::streams[0]=r::StreamPeer{};r::live=r::Live{};r::sending=false;r::fault_until=0;r::acks[0]=0;r::ack_seen[0]=false;r::engine_sequence=100;
 auto&peer=r::saved.peers[0];const std::uint8_t screen[]={2,170,187,204,221,238};std::memcpy(peer.mac,screen,6);std::strcpy(peer.name,"Independent native peer");for(unsigned n=0;n<16;++n)peer.key[n]=n;
 advance(20000000);check(r::prepare_stream(0));auto good=captured();publish(good);input(capability(1,5,7));r::streams[0].capabilities.sent();r::maintain_streams(r::now());sensor_ack(1);check(!r::radio_fault(20000000));
 // Sensor ACKs cannot cover a missing complete-engine ACK family.
 advance(23000001);flex_off_live(good);sensor_ack(2);r::maintain_streams(r::now());check(r::ack_seen[0]&&!r::streams[0].engine_ack_seen);check(r::radio_fault(20000000));r::led(true,true);check(requested_pattern==ecu::status_led::Pattern::Problem);
 slot(2);const auto seq=r::streams[0].pair.sequence();finish();acknowledgement(seq);check(!r::streams[0].engine_ack_seen);advance(23050001);slot(3);finish();acknowledgement(seq);check(r::streams[0].engine_ack_seen&&!r::radio_fault(20000000));
 advance(26050002);flex_off_live(good);sensor_ack(3);check(r::radio_fault(20000000));
 // Disable negotiates family removal; fresh sensor ACK can then cover link.
 auto disable=capability(2,5,8);w::u32(disable.data()+32,0);w::u32(disable.data()+36,0);check(r::hmac(peer.key,disable.data(),44,disable.data()+44));input(disable);r::streams[0].capabilities.sent();r::maintain_streams(r::now());check(!r::streams[0].capabilities.engine()&&!r::streams[0].engine_expected_since);check(!r::radio_fault(20000000));
 // Key reset and stalled callback cannot retain an old pending pair/window.
 input(capability(3,5,9));r::streams[0].capabilities.sent();advance(26100000);flex_off_live(good);slot(2);check(r::sending&&r::streams[0].pair.pending());const auto old=r::streams[0].pair.sequence();advance(26350001);r::maintain_streams(r::now());check(!r::streams[0].pair.pending()&&r::sending);check(!r::streams[0].engine_sent.acknowledge(old,r::now()));finish();
 advance(26400000);slot(2);finish();check(r::streams[0].pair.pending());check(r::prepare_stream(0));check(!r::streams[0].pair.pending()&&!r::streams[0].engine_ack_seen&&!r::streams[0].capabilities.engine());
 input(capability(1,5,10));r::streams[0].capabilities.sent();r::engine_sequence=UINT64_MAX;auto attempts=fake_datagrams.size();slot(2);check(fake_datagrams.size()==attempts&&r::engine_sequence==UINT64_MAX&&r::fault_until>r::now());
 // Age arithmetic saturates to unknown on time reversal and addition overflow.
 check(w::transmitted_age_us(0,10,9)==UINT64_MAX);check(w::transmitted_age_us(UINT64_MAX-1,10,12)==UINT64_MAX);check(w::transmitted_age_us(1,10,11)==2);
 std::cout<<"independent_sender_total_checks "<<checks<<'\n';
}
