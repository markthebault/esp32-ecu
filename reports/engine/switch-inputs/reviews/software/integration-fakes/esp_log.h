#pragma once
inline void review_log(const char*,const char*,...){}
inline const char*esp_err_to_name(int){return "fixture";}
#define ESP_LOGE(...) review_log(__VA_ARGS__)
#define ESP_LOGI(...) review_log(__VA_ARGS__)
