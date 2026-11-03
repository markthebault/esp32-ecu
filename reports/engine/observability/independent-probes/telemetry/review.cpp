#include "ecu/engine_radio.hpp"
#include <openssl/hmac.h>
namespace {
ecu::radio::wire::PeerCapabilities caps;
const std::uint8_t lmk[16]={0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15};
const std::uint8_t nonce[16]={16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31};
bool mac(const std::uint8_t*k,unsigned n,const std::uint8_t*b,unsigned size,std::uint8_t*out){unsigned count=0;return HMAC(EVP_sha256(),k,n,b,size,out,&count)&&count==32;}
}
extern "C" void reset(){caps.reset();}
extern "C" int reply(const std::uint8_t*request,unsigned length,std::uint64_t floor,std::uint64_t sent,std::uint8_t*out){
 std::uint8_t proof[32];if(length!=ecu::radio::wire::capability_size||!mac(lmk,16,request,44,proof)||!ecu::radio::wire::same(proof,request+44,32)||!caps.request(request,length,123))return 0;
 caps.reply(out,123,nonce,floor,sent);return mac(lmk,16,out,76,out+76);
}
extern "C" int frame(std::uint64_t packet,std::uint64_t observation,std::uint32_t sample_age,std::uint32_t control_age,std::uint32_t worker_age,std::uint64_t sent,std::uint8_t*out){
 ecu::engine::Tune tune;ecu::engine::Inputs in;in.rpm=1000;in.map_kpa=45;in.tps_pct=10;in.clt_c=85;in.iat_c=25;in.lambda=1;in.battery_v=14;in.sensor_v=5;in.sampled_us=10;in.synced=in.sensors_valid=in.lambda_ready=true;
 ecu::engine::Controller c;auto o=c.step(tune,in,10);ecu::engine::RuntimeSample r;ecu::engine::data_values(r,in,o);r.sequence=observation;r.control_us=r.sampled_us=10;r.tune_revision=r.sensor_revision=1;r.input_valid=255;r.flags|=ecu::engine::InputsFresh|ecu::engine::StorageOk|ecu::engine::CrankSynced|ecu::engine::InputsQualified;r.source=ecu::engine::DataSource::Target;r.worker_sequence=1;r.worker_observed_us=10;
 const auto transcript=ecu::radio::wire::engine_key_transcript(nonce,123);std::uint8_t key[32];return mac(lmk,16,transcript.data(),transcript.size(),key)&&ecu::radio::wire::engine_body(out,r,123,packet,sample_age,control_age,worker_age,sent)&&mac(key,32,out,200,out+200);
}
