#include "ecu/engine_storage.hpp"
#include <cassert>
#include <iostream>
#include <map>
#include <string>
// API model only. It tests the caller's operations/error handling, not ESP-IDF
// flash algorithms, wear, power-fail atomicity or a real partition's capacity.
namespace {
struct Store {bool legacy_exists=false;std::string legacy,blob;bool blob_exists=false,wrong_type=false;esp_err_t init_error=ESP_OK,commit_error=ESP_OK,write_error=ESP_OK;unsigned writes=0,commits=0,closes=0;std::string pending;};
Store store;
void reset(){store=Store{};}
auto valid=[](const std::string&s){return s.size()>=2&&s.front()=='{'&&s.back()=='}';};
std::string large(){return "{\"padding\":\""+std::string(12000,'x')+"\"}";}
}
esp_err_t nvs_flash_init_partition(const char*label){assert(std::string(label)=="engine_nvs");return store.init_error;}
esp_err_t nvs_open(const char*ns,nvs_open_mode_t mode,nvs_handle_t*h){assert(std::string(ns)=="ecu_engine"&&mode==NVS_READONLY);if(!store.legacy_exists)return ESP_ERR_NVS_NOT_FOUND;*h=1;return ESP_OK;}
esp_err_t nvs_open_from_partition(const char*p,const char*ns,nvs_open_mode_t mode,nvs_handle_t*h){assert(std::string(p)=="engine_nvs"&&std::string(ns)=="ecu_engine"&&mode==NVS_READWRITE);*h=2;return ESP_OK;}
esp_err_t nvs_get_str(nvs_handle_t h,const char*key,char*out,std::size_t*size){
 assert(h==1&&std::string(key)=="tune");const auto length=store.legacy.size()+1;
 if(out){if(*size<length)return ESP_ERR_NVS_INVALID_LENGTH;std::memcpy(out,store.legacy.c_str(),length);}*size=length;return ESP_OK;
}
esp_err_t nvs_get_blob(nvs_handle_t h,const char*key,void*out,std::size_t*size){
 assert(h==2&&std::string(key)=="tune");if(store.wrong_type)return ESP_ERR_NVS_TYPE_MISMATCH;if(!store.blob_exists)return ESP_ERR_NVS_NOT_FOUND;
 if(out){if(*size<store.blob.size())return ESP_ERR_NVS_INVALID_LENGTH;std::memcpy(out,store.blob.data(),store.blob.size());}*size=store.blob.size();return ESP_OK;
}
esp_err_t nvs_set_blob(nvs_handle_t h,const char*key,const void*value,std::size_t size){assert(h==2&&std::string(key)=="tune");++store.writes;if(store.write_error)return store.write_error;store.pending.assign(static_cast<const char*>(value),size);return ESP_OK;}
esp_err_t nvs_commit(nvs_handle_t h){assert(h==2);++store.commits;if(store.commit_error)return store.commit_error;store.blob=store.pending;store.blob_exists=true;return ESP_OK;}
void nvs_close(nvs_handle_t){++store.closes;}
int main(){
 using namespace ecu::engine_storage;std::string out;esp_err_t error;
 reset();assert(load(out,valid,error)==Load::Missing);assert(error==ESP_OK&&store.writes==0);
 // Full maps exceed the SDK's documented 4000-byte string ceiling.
 const auto document=large();assert(document.size()>4000&&document.size()<maximum);
 assert(save(document)==ESP_OK);assert(store.blob==document&&store.commits==1);
 out.clear();assert(load(out,valid,error)==Load::Loaded&&out==document);
 // Migration copies a validated legacy string; it never removes that record.
 reset();store.legacy_exists=true;store.legacy="{\"revision\":1}";const auto legacy=store.legacy;
 assert(load(out,valid,error)==Load::Migrated);assert(out==legacy&&store.legacy==legacy&&store.blob==legacy);
 const auto writes=store.writes;assert(load(out,valid,error)==Load::Loaded);assert(store.writes==writes);
 // New corrupted data does not fall back to, overwrite or delete a legacy tune.
 for(const auto&bad:{std::string{},std::string("bad"),std::string("{}\0junk",7),std::string(maximum+1,'x')}){
  reset();store.legacy_exists=true;store.legacy=legacy;store.blob_exists=true;store.blob=bad;out="unchanged";
  assert(load(out,valid,error)==Load::Error&&out=="unchanged"&&store.writes==0&&store.legacy==legacy);
 }
 reset();store.wrong_type=true;assert(load(out,valid,error)==Load::Error&&store.writes==0);
 reset();store.legacy_exists=true;store.legacy="{broken";assert(load(out,valid,error)==Load::Error&&store.writes==0);
 reset();store.legacy_exists=true;store.legacy=std::string("{}\0junk",7);assert(load(out,valid,error)==Load::Error&&store.writes==0);
 for(bool commit_failure:{false,true}){
  reset();store.legacy_exists=true;store.legacy=legacy;out="unchanged";
  (commit_failure?store.commit_error:store.write_error)=ESP_ERR_NVS_NOT_ENOUGH_SPACE;
  assert(load(out,valid,error)==Load::Error&&out=="unchanged"&&store.legacy==legacy);
 }
 reset();store.init_error=ESP_ERR_NVS_NOT_ENOUGH_SPACE;assert(load(out,valid,error)==Load::Error&&store.writes==0);
 reset();assert(save(std::string(maximum+1,'x'))==ESP_ERR_NVS_INVALID_LENGTH&&store.writes==0);
 assert(save(std::string("{}\0junk",7))==ESP_ERR_NVS_INVALID_LENGTH&&store.writes==0);
 std::cout<<"Engine NVS API-model tests passed: large blobs, retained legacy migration, corrupt data, size/NUL checks and write/init/commit errors\n";
}
