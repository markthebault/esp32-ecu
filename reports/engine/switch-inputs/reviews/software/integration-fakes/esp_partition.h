#pragma once
struct esp_partition_t {unsigned address,size;};
constexpr unsigned ESP_PARTITION_TYPE_DATA=1,ESP_PARTITION_SUBTYPE_DATA_NVS=2;
const esp_partition_t*esp_partition_find_first(unsigned,unsigned,const char*);
