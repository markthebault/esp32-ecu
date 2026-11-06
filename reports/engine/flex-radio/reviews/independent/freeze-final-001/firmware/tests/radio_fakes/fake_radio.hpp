#pragma once
// Native API model only. No ESP-IDF/RTOS/Wi-Fi/RF or physical GPIO execution.
#include "fake_target.hpp"
#include <openssl/hmac.h>
inline std::int64_t fake_radio_now=5000000;
inline std::uint64_t fake_mac_delay_us=0;
inline bool fake_mac_error=false;
inline int fake_send_error=ESP_OK;
inline unsigned fake_deleted_peers=0;
struct FakeDatagram {std::array<std::uint8_t,6> mac;std::vector<std::uint8_t> bytes;std::int64_t stamp;int result;};
inline std::vector<FakeDatagram> fake_datagrams;
inline std::int64_t esp_timer_get_time(){return fake_radio_now;}
constexpr int GPIO_PULLUP_ENABLE=1,GPIO_NUM_0=0;
inline int gpio_get_level(gpio_num_t){return 1;}
inline int xQueueSend(QueueHandle_t q,const void*in,unsigned){return xQueueSendFromISR(q,in,nullptr);}
inline int xTaskCreate(void(*)(void*),const char*,unsigned,void*,unsigned,TaskHandle_t*){return pdPASS;}
inline void vTaskDelay(unsigned){assert(false&&"Native radio test does not execute the infinite RTOS task");}
struct wifi_tx_info_t{};using esp_now_send_status_t=int;
constexpr int ESP_NOW_SEND_SUCCESS=0,ESP_NOW_SEND_FAIL=1,WIFI_IF_STA=0,WIFI_SECOND_CHAN_NONE=0,WIFI_PS_NONE=0,WIFI_STORAGE_RAM=0,WIFI_MODE_STA=1,ESP_ERR_WIFI_NOT_INIT=0x3001;
using wifi_mode_t=int;struct wifi_init_config_t{};
#define WIFI_INIT_CONFIG_DEFAULT() wifi_init_config_t{}
struct esp_now_recv_info_t {const std::uint8_t*src_addr;};
struct esp_now_peer_info_t {std::uint8_t peer_addr[6];int channel,ifidx;bool encrypt;std::uint8_t lmk[16];};
inline int esp_now_send(const std::uint8_t*mac,const std::uint8_t*data,unsigned length){
 assert(length<=250);FakeDatagram d{};std::memcpy(d.mac.data(),mac,6);d.bytes.assign(data,data+length);d.stamp=fake_radio_now;d.result=fake_send_error;fake_datagrams.push_back(d);return fake_send_error;
}
inline bool esp_now_is_peer_exist(const std::uint8_t*){return false;}
inline int esp_now_add_peer(const esp_now_peer_info_t*){return ESP_OK;}
inline int esp_now_mod_peer(const esp_now_peer_info_t*){return ESP_OK;}
inline int esp_now_del_peer(const std::uint8_t*){++fake_deleted_peers;return ESP_OK;}
inline int esp_now_init(){return ESP_OK;}
inline int esp_now_set_pmk(const std::uint8_t*){return ESP_OK;}
inline int esp_now_register_send_cb(void(*)(const wifi_tx_info_t*,esp_now_send_status_t)){return ESP_OK;}
inline int esp_now_register_recv_cb(void(*)(const esp_now_recv_info_t*,const std::uint8_t*,int)){return ESP_OK;}
inline int esp_wifi_get_mode(wifi_mode_t*mode){*mode=WIFI_MODE_STA;return ESP_OK;}
inline int esp_wifi_init(const wifi_init_config_t*){return ESP_OK;}
inline int esp_wifi_set_storage(int){return ESP_OK;}
inline int esp_wifi_set_mode(int){return ESP_OK;}
inline int esp_wifi_start(){return ESP_OK;}
inline int esp_wifi_set_channel(unsigned,int){return ESP_OK;}
inline int esp_wifi_set_ps(int){return ESP_OK;}
inline int esp_wifi_get_mac(int,std::uint8_t*mac){const std::uint8_t own[]={2,236,0,0,0,1};std::memcpy(mac,own,6);return ESP_OK;}
inline int esp_netif_init(){return ESP_OK;}
inline int esp_event_loop_create_default(){return ESP_OK;}
inline void*esp_netif_create_default_wifi_sta(){return nullptr;}
inline std::uint32_t esp_random(){return 0x12345678;}
inline void esp_fill_random(void*out,unsigned n){auto*p=static_cast<std::uint8_t*>(out);for(unsigned i=0;i<n;++i)p[i]=i+1;}
struct mbedtls_md_info_t{};constexpr int MBEDTLS_MD_SHA256=1;
inline const mbedtls_md_info_t*mbedtls_md_info_from_type(int){static const mbedtls_md_info_t info;return &info;}
inline int mbedtls_md_hmac(const mbedtls_md_info_t*,const unsigned char*key,std::size_t key_size,const unsigned char*data,std::size_t length,unsigned char*out){
 fake_radio_now+=fake_mac_delay_us;fake_now+=fake_mac_delay_us;
 if(fake_mac_error)return -1;
 unsigned n=0;return HMAC(EVP_sha256(),key,static_cast<int>(key_size),data,length,out,&n)&&n==32?0:-1;
}
