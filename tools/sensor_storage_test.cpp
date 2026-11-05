// The actual storage helper/parser against an NVS API model. No flash capacity,
// wear, SDK recovery or power-fail atomicity is modeled.
#include "ecu/config_storage.hpp"
#include "config_json.hpp"
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>

namespace {
struct Store {
 bool legacy_exists=false,blob_exists=false,wrong_type=false;
 std::string legacy,blob,pending;
 esp_err_t open_error=ESP_OK,read_error=ESP_OK,write_error=ESP_OK,commit_error=ESP_OK;
 unsigned writes=0,commits=0,closes=0;
} store;
unsigned checks=0;
void check(bool ok,const char*why){++checks;if(!ok)throw std::runtime_error(why);}
std::string file(const char*name){std::ifstream f(name);return {(std::istreambuf_iterator<char>(f)),{}};}
bool valid(const std::string&text){
 if(!ecu::web::safe_json(text.c_str(),text.size()))return false;
 auto*j=cJSON_ParseWithOpts(text.c_str(),nullptr,true);ecu::config::Config c;
 const bool ok=j&&ecu::web::parse(j,c);cJSON_Delete(j);return ok;
}
std::string normalized(const std::string&text){
 auto*j=cJSON_Parse(text.c_str());ecu::config::Config c;
 check(j&&ecu::web::parse(j,c)&&ecu::web::upgrade_profile_document(j),"actual boundary fixture upgrades");
 auto*encoded=cJSON_PrintUnformatted(j);check(encoded,"canonical profile allocated");
 const std::string out(encoded);cJSON_free(encoded);cJSON_Delete(j);return out;
}
}
esp_err_t nvs_open(const char*ns,nvs_open_mode_t mode,nvs_handle_t*out){
 check(std::string(ns)=="ecu_config","existing sensor namespace retained");
 if(store.open_error)return store.open_error;
 if(mode==NVS_READONLY&&!store.legacy_exists&&!store.blob_exists&&!store.wrong_type)return ESP_ERR_NVS_NOT_FOUND;
 *out=1;return ESP_OK;
}
esp_err_t nvs_get_blob(nvs_handle_t,const char*key,void*out,std::size_t*size){
 check(std::string(key)=="profile_blob","separate bounded blob key");
 if(store.wrong_type)return ESP_ERR_NVS_TYPE_MISMATCH;
 if(!store.blob_exists)return ESP_ERR_NVS_NOT_FOUND;
 if(store.read_error)return store.read_error;
 if(out){if(*size<store.blob.size())return ESP_ERR_NVS_INVALID_LENGTH;std::memcpy(out,store.blob.data(),store.blob.size());}
 *size=store.blob.size();return ESP_OK;
}
esp_err_t nvs_get_str(nvs_handle_t,const char*key,char*out,std::size_t*size){
 check(std::string(key)=="profile","legacy record remains read-only");
 if(!store.legacy_exists)return ESP_ERR_NVS_NOT_FOUND;
 if(store.read_error)return store.read_error;
 const auto length=store.legacy.size()+1;
 if(out){if(*size<length)return ESP_ERR_NVS_INVALID_LENGTH;std::memcpy(out,store.legacy.c_str(),length);}
 *size=length;return ESP_OK;
}
esp_err_t nvs_set_blob(nvs_handle_t,const char*key,const void*data,std::size_t size){
 check(std::string(key)=="profile_blob","save never overwrites legacy key");++store.writes;
 if(store.write_error)return store.write_error;
 store.pending.assign(static_cast<const char*>(data),size);return ESP_OK;
}
esp_err_t nvs_commit(nvs_handle_t){
 ++store.commits;if(store.commit_error)return store.commit_error;
 store.blob=store.pending;store.blob_exists=true;return ESP_OK;
}
void nvs_close(nvs_handle_t){++store.closes;}

int main(int argc,char**argv){
 try{
  if(argc!=2)return 2;
  using namespace ecu::config_storage;
  const auto legacy=file(argv[1]);const auto document=normalized(legacy);
  check(legacy.size()+1<=4000&&document.size()+1>4000,"reviewed legacy-to-new string ceiling regression reproduced");
  check(valid(legacy)&&valid(document),"old and upgraded profiles validate");
  std::string out="unchanged";esp_err_t error;
  check(load(out,valid,error)==Load::Missing&&error==ESP_OK&&out=="unchanged"&&store.writes==0,"missing storage is read-only");
  store.legacy_exists=true;store.legacy=legacy;
  check(load(out,valid,error)==Load::Legacy&&out==legacy&&store.writes==0,"boot retains old bytes and does not migrate flash");
  check(save(document.data(),document.size())==ESP_OK,"upgraded profile larger than4k saves as blob");
  check(store.legacy==legacy&&store.blob==document&&store.commits==1,"successful save retains legacy and publishes new blob");
  out.clear();check(load(out,valid,error)==Load::Blob&&out==document&&store.writes==1,"blob has priority over retained legacy");
  for(const auto&bad:{std::string{},std::string("{bad"),std::string("{}\0junk",7),std::string(maximum+1,'x')}){
   store={};store.legacy_exists=true;store.legacy=legacy;store.blob_exists=true;store.blob=bad;out="unchanged";
   check(load(out,valid,error)==Load::Error&&out=="unchanged"&&store.writes==0&&store.legacy==legacy,"present corrupt blob cannot roll back or overwrite legacy");
  }
  store={};store.wrong_type=true;check(load(out,valid,error)==Load::Error&&store.writes==0,"wrong blob type blocks writes");
  store={};store.legacy_exists=true;store.legacy=std::string("{}\0junk",7);check(load(out,valid,error)==Load::Error&&store.writes==0,"embedded NUL in legacy blocks load");
  store={};store.blob_exists=true;store.blob=document;store.read_error=ESP_ERR_NVS_NOT_ENOUGH_SPACE;
  check(load(out,valid,error)==Load::Error&&store.writes==0,"read failure retains record");
  for(bool commit_failure:{false,true}){
   store={};store.legacy_exists=true;store.legacy=legacy;store.blob_exists=true;store.blob=document;
   (commit_failure?store.commit_error:store.write_error)=ESP_ERR_NVS_NOT_ENOUGH_SPACE;
   const auto writes=store.writes;
   check(save(document.data(),document.size())==ESP_ERR_NVS_NOT_ENOUGH_SPACE&&store.legacy==legacy&&store.blob==document,"write/commit failure does not publish in this API model");
   check(store.writes==writes+1&&store.commits==unsigned(commit_failure),"failure ends the write sequence");
  }
  store={};store.open_error=ESP_ERR_NVS_NOT_ENOUGH_SPACE;
  check(save(document.data(),document.size())==store.open_error&&store.writes==0,"open failure cannot write");
  store={};const std::string large(maximum,'x');
  check(save(large.data(),large.size())==ESP_OK,"inclusive16KiB blob helper boundary");
  check(save(large.data(),large.size()+1)==ESP_ERR_NVS_INVALID_LENGTH,"oversize rejected before reading body");
  check(save("{}\0x",4)==ESP_ERR_NVS_INVALID_LENGTH,"embedded NUL save rejects");
  check(save(nullptr,2)==ESP_ERR_NVS_INVALID_LENGTH&&save("",0)==ESP_ERR_NVS_INVALID_LENGTH,"null/empty save rejects");
  std::cout<<checks<<" sensor NVS API-model checks passed; legacy="<<legacy.size()<<"B normalized="<<document.size()<<"B\n";
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
}
