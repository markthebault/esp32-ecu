#include "ecu/espnow_protocol.hpp"
#include <cassert>
#include <iostream>
#include <openssl/hmac.h>
using namespace ecu::radio::wire;
int main(){
 std::uint8_t p[96]{};header(p,Request,96);assert(valid(p,96,Request,96));assert(!valid(p,95,Request,96));assert(!valid(p,96,Telemetry,96));p[4]=2;assert(!valid(p,96,Request,96));
 u32(p,0xfedcba98);assert(read32(p)==0xfedcba98);f32(p,12.5);assert(read32(p)==0x41480000);
 std::uint8_t zero[16]{},mac[6]={2,1,2,3,4,5};assert(!unicast(zero));assert(unicast(mac));mac[0]=255;assert(!unicast(mac));mac[0]=2;
 auto t=transcript(zero,mac,mac,zero,p);assert(t.size()==83);assert(!std::memcmp(t.data(),"ECU-NOW-PAIR-v1",15));assert(same(t.data()+31,mac,6));assert(same(t.data()+37,mac,6));
 // Cross-language pairing golden vector: the embedded firmware uses mbedTLS,
 // this host check independently uses OpenSSL against the Python receiver codec.
 std::uint8_t win[16],setup[16],nonce[16],ecu_mac[6]={2,236,0,0,0,1},screen_mac[6]={2,236,0,0,1,1},name[24]{};
 for(unsigned i=0;i<16;++i){win[i]=i;setup[i]=i+16;nonce[i]=i+32;}
 std::memcpy(name,"Screen",6);auto auth=transcript(win,ecu_mac,screen_mac,nonce,name);
 std::uint8_t digest[32];unsigned length=0;
 HMAC(EVP_sha256(),setup,16,auth.data(),auth.size(),digest,&length);assert(length==32);
 const std::uint8_t proof[]={0xfa,0x0d,0x4b,0xed,0x65,0x4e,0x65,0xe1,0x65,0x83,0x14,0xa5,0xf3,0x5d,0x81,0xf2,0xfa,0x10,0x0c,0xde,0x0e,0xc8,0xde,0x0e,0xca,0x0f,0x07,0x1d,0x42,0xf8,0xe1,0xb9};
 assert(same(digest,proof,32));auth[0]='K';HMAC(EVP_sha256(),setup,16,auth.data(),auth.size(),digest,&length);
 const std::uint8_t lmk[]={0x7c,0xa9,0x9a,0x48,0x8a,0x7d,0xbb,0x3d,0x18,0x4b,0x20,0x86,0x49,0xf4,0x76,0x81};assert(same(digest,lmk,16));
 Button button;using A=Button;
 assert(button.poll(true,0)==A::None);assert(button.poll(true,4000)==A::None); // held at boot never opens
 button.poll(false,4010);button.poll(false,4050);
 button.poll(true,4100);button.poll(true,4140);assert(button.poll(true,7140)==A::Open);assert(button.poll(true,11000)==A::None);button.poll(false,11010);assert(button.poll(false,11050)==A::None);
 button.poll(true,11100);button.poll(true,11140);button.poll(false,11300);assert(button.poll(false,11340)==A::Confirm);
 button.poll(true,12000);button.poll(false,12010);assert(button.poll(false,12100)==A::None); // bounce
 std::cout<<"ESP-NOW wire framing, endianness, MAC validation, pairing HMAC golden vectors and button timing passed\n";
}
