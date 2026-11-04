#pragma once
constexpr int ESP_PARTITION_TYPE_DATA=1,ESP_PARTITION_SUBTYPE_DATA_NVS=2;
struct esp_partition_t {unsigned address,size;};
inline const esp_partition_t*esp_partition_find_first(int,int,const char*){static const esp_partition_t p{0x210000,0x20000};return &p;}
