#pragma once
#include "fake_radio.hpp"
using nvs_handle_t=unsigned;
constexpr int NVS_READWRITE=1,ESP_ERR_NVS_NOT_FOUND=0x1102;
inline std::vector<std::uint8_t> fake_peer_blob;
inline int nvs_open(const char*,int,nvs_handle_t*h){*h=1;return ESP_OK;}
inline int nvs_get_blob(nvs_handle_t,const char*,void*,std::size_t*){return ESP_ERR_NVS_NOT_FOUND;}
inline int nvs_set_blob(nvs_handle_t,const char*,const void*data,std::size_t n){auto*p=static_cast<const std::uint8_t*>(data);fake_peer_blob.assign(p,p+n);return ESP_OK;}
inline int nvs_commit(nvs_handle_t){return ESP_OK;}
inline void nvs_close(nvs_handle_t){}
