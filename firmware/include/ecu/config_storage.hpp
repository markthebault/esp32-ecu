#pragma once
#include "nvs.h"
#include <cstring>
#include <string>
#include <utility>

namespace ecu::config_storage {
constexpr std::size_t maximum=16384;
constexpr const char* name_space="ecu_config";
constexpr const char* blob_key="profile_blob";
enum class Load {Missing,Blob,Legacy,Error};

// Boot is read-only. A present invalid blob must not silently roll back to the
// retained legacy string. Never erase/delete; SDK recovery and actual flash
// capacity/power-fail behavior still require physical validation.
template<class Validate>Load load(std::string&out,Validate validate,esp_err_t&error){
 nvs_handle_t handle{};error=nvs_open(name_space,NVS_READONLY,&handle);
 if(error==ESP_ERR_NVS_NOT_FOUND){error=ESP_OK;return Load::Missing;}
 if(error!=ESP_OK)return Load::Error;
 std::size_t size=0;error=nvs_get_blob(handle,blob_key,nullptr,&size);
 Load result=Load::Error;
 if(error==ESP_OK){
  if(!size||size>maximum)error=ESP_ERR_NVS_INVALID_LENGTH;
  else{
   std::string saved(size,'\0');error=nvs_get_blob(handle,blob_key,saved.data(),&size);
   if(error==ESP_OK&&size==saved.size()&&!std::memchr(saved.data(),0,size)&&validate(saved)){
    out=std::move(saved);result=Load::Blob;
   }else if(error==ESP_OK)error=ESP_ERR_NVS_INVALID_LENGTH;
  }
 }else if(error==ESP_ERR_NVS_NOT_FOUND){
  error=nvs_get_str(handle,"profile",nullptr,&size);
  if(error==ESP_ERR_NVS_NOT_FOUND){error=ESP_OK;result=Load::Missing;}
  else if(error==ESP_OK){
   if(size<2||size>maximum+1)error=ESP_ERR_NVS_INVALID_LENGTH;
   else{
    std::string saved(size,'\0');error=nvs_get_str(handle,"profile",saved.data(),&size);
    if(error==ESP_OK&&size==saved.size()&&saved.back()=='\0'&&
       std::strlen(saved.c_str())==size-1){
     saved.pop_back();
     if(validate(saved)){out=std::move(saved);result=Load::Legacy;}
     else error=ESP_ERR_NVS_INVALID_LENGTH;
    }else if(error==ESP_OK)error=ESP_ERR_NVS_INVALID_LENGTH;
   }
  }
 }
 nvs_close(handle);return result;
}
inline esp_err_t save(const char*document,std::size_t size){
 if(!document||!size||size>maximum||std::memchr(document,0,size))return ESP_ERR_NVS_INVALID_LENGTH;
 nvs_handle_t handle{};auto error=nvs_open(name_space,NVS_READWRITE,&handle);
 if(error==ESP_OK){
  error=nvs_set_blob(handle,blob_key,document,size);
  if(error==ESP_OK)error=nvs_commit(handle);
  nvs_close(handle);
 }
 return error;
}
}
