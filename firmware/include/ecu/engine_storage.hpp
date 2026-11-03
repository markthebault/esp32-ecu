#pragma once
#include "nvs.h"
#include "nvs_flash.h"
#include <cstring>
#include <string>
#include <utility>
#include "ecu/engine_limits.hpp"
namespace ecu::engine_storage {
constexpr const char* partition="engine_nvs";
constexpr const char* name_space="ecu_engine";
constexpr std::size_t maximum=engine::tune_maximum;
// Engine maps can exceed NVS's 4000-byte string limit. A dedicated 64 KiB
// partition holds bounded blobs without moving existing sensor/peer storage.
// This helper never requests erase/delete. NVS's own recovery can discard
// physically corrupt entries; this is not raw-flash forensic preservation.
enum class Load {Missing,Loaded,Migrated,Error};
inline bool read_legacy(std::string&out,esp_err_t&error){
 nvs_handle_t legacy{};error=nvs_open(name_space,NVS_READONLY,&legacy);
 if(error==ESP_ERR_NVS_NOT_FOUND)return false;
 if(error!=ESP_OK)return false;
 std::size_t size=0;error=nvs_get_str(legacy,"tune",nullptr,&size);
 if(error==ESP_OK){
  if(size<2||size>maximum+1)error=ESP_ERR_NVS_INVALID_LENGTH;
  else{
   std::string saved(size,'\0');error=nvs_get_str(legacy,"tune",saved.data(),&size);
   if(error==ESP_OK){
    if(size!=saved.size()||saved.back()!='\0'||std::strlen(saved.c_str())!=size-1)error=ESP_ERR_NVS_INVALID_LENGTH;
    else out.assign(saved.data(),size-1);
   }
  }
 }
 nvs_close(legacy);return error==ESP_OK;
}
template<class Validate>Load load(std::string&out,Validate validate,esp_err_t&error){
 error=nvs_flash_init_partition(partition);if(error!=ESP_OK)return Load::Error;
 nvs_handle_t handle{};error=nvs_open_from_partition(partition,name_space,NVS_READWRITE,&handle);
 if(error!=ESP_OK)return Load::Error;
 std::size_t size=0;error=nvs_get_blob(handle,"tune",nullptr,&size);
 Load result=Load::Error;
 if(error==ESP_OK){
  if(size==0||size>maximum)error=ESP_ERR_NVS_INVALID_LENGTH;
  else{
   std::string saved(size,'\0');error=nvs_get_blob(handle,"tune",saved.data(),&size);
   if(error==ESP_OK&&size==saved.size()&&std::strlen(saved.c_str())==size&&validate(saved)){
    out=std::move(saved);result=Load::Loaded;
   }else if(error==ESP_OK)error=ESP_ERR_NVS_INVALID_LENGTH;
  }
 }else if(error==ESP_ERR_NVS_NOT_FOUND){
  std::string saved;
  if(read_legacy(saved,error)){
   if(!validate(saved))error=ESP_ERR_NVS_INVALID_LENGTH;
   else{
    error=nvs_set_blob(handle,"tune",saved.data(),saved.size());
    if(error==ESP_OK)error=nvs_commit(handle);
    if(error==ESP_OK){out=std::move(saved);result=Load::Migrated;}
   }
  }else if(error==ESP_ERR_NVS_NOT_FOUND){error=ESP_OK;result=Load::Missing;}
 }
 nvs_close(handle);return result;
}
inline esp_err_t save(const std::string&document){
 if(document.empty()||document.size()>maximum||std::strlen(document.c_str())!=document.size())return ESP_ERR_NVS_INVALID_LENGTH;
 nvs_handle_t handle{};auto error=nvs_open_from_partition(partition,name_space,NVS_READWRITE,&handle);
 if(error==ESP_OK){error=nvs_set_blob(handle,"tune",document.data(),document.size());if(error==ESP_OK)error=nvs_commit(handle);nvs_close(handle);}
 return error;
}
}
