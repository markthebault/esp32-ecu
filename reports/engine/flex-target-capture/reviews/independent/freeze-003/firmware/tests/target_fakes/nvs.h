#pragma once
#include "fake_target.hpp"
#include <cstddef>
using nvs_handle_t=unsigned;
constexpr esp_err_t ESP_ERR_NVS_NOT_FOUND=1,ESP_ERR_NVS_INVALID_LENGTH=2;
enum nvs_open_mode_t {NVS_READONLY,NVS_READWRITE};
inline esp_err_t nvs_open(const char*,nvs_open_mode_t,nvs_handle_t*){return ESP_ERR_NVS_NOT_FOUND;}
inline esp_err_t nvs_open_from_partition(const char*,const char*,nvs_open_mode_t,nvs_handle_t*h){*h=1;return ESP_OK;}
inline esp_err_t nvs_get_str(nvs_handle_t,const char*,char*,std::size_t*){return ESP_ERR_NVS_NOT_FOUND;}
inline esp_err_t nvs_get_blob(nvs_handle_t,const char*,void*,std::size_t*){return ESP_ERR_NVS_NOT_FOUND;}
inline esp_err_t nvs_set_blob(nvs_handle_t,const char*,const void*,std::size_t){return ESP_OK;}
inline esp_err_t nvs_commit(nvs_handle_t){return ESP_OK;}
inline void nvs_close(nvs_handle_t){}
