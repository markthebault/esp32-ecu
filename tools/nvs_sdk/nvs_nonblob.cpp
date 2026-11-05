#include "nvs_storage.hpp"
#include "spi_flash_mmap.h"
#include <vector>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <cstdio>
struct Memory: nvs::Partition {
 std::vector<unsigned char> bytes=std::vector<unsigned char>(32*4096,255);
 unsigned writes=0,erases=0,reads=0;long fail_after=-1;
 const char*get_partition_name()override{return "engine_nvs";}
 esp_err_t read_raw(size_t o,void*d,size_t n)override{assert(o+n<=bytes.size());++reads;std::memcpy(d,bytes.data()+o,n);return ESP_OK;}
 esp_err_t read(size_t o,void*d,size_t n)override{return read_raw(o,d,n);}
 esp_err_t write_raw(size_t o,const void*d,size_t n)override{assert(o+n<=bytes.size());if(fail_after==0)return ESP_ERR_FLASH_OP_FAIL;if(fail_after>0)--fail_after;++writes;const auto*p=static_cast<const unsigned char*>(d);for(size_t i=0;i<n;++i){assert((bytes[o+i]&p[i])==p[i]);bytes[o+i]&=p[i];}return ESP_OK;}
 esp_err_t write(size_t o,const void*d,size_t n)override{return write_raw(o,d,n);}
 esp_err_t erase_range(size_t o,size_t n)override{assert(o+n<=bytes.size()&&o%4096==0&&n%4096==0);if(fail_after==0)return ESP_ERR_FLASH_OP_FAIL;if(fail_after>0)--fail_after;++erases;std::memset(bytes.data()+o,255,n);return ESP_OK;}
 uint32_t get_address()override{return 0x210000;}
 uint32_t get_size()override{return bytes.size();}
 bool get_readonly()override{return false;}
};
std::vector<unsigned char> data(unsigned size,unsigned seed){std::vector<unsigned char> v(size);for(unsigned n=0;n<size;++n)v[n]=1+(n*17+seed*53)%254;return v;}
static unsigned checks=0;
void verify(bool b,const char*expr,unsigned line){++checks;if(!b)std::cerr<<line<<": "<<expr<<"\n";assert(b);}
#define require(v) verify(v,#v,__LINE__)

int main(int argc,char**argv){
 FILE*ledger=argc>1?std::fopen(argv[1],"wx"):nullptr;if(argc>1)require(ledger!=nullptr);
 unsigned trials=0,old_count=0,new_count=0;
 for(unsigned kind=0;kind<3;++kind){
  Memory baseline;uint8_t ns;uint32_t old_scalar=0x12345678,new_scalar=0x87654321;
  const char old_text[]="previous confirmed text",new_text[]="replacement confirmed text";
  const auto old_blob=data(64,22),new_blob=data(64,23);
  {nvs::Storage store(&baseline);require(store.init(0,32)==ESP_OK);require(store.createOrOpenNamespace("ecu_engine",true,ns)==ESP_OK);
   if(kind==0)require(store.writeItem(ns,nvs::ItemType::U32,"key",&old_scalar,sizeof(old_scalar))==ESP_OK);
   if(kind==1)require(store.writeItem(ns,nvs::ItemType::SZ,"key",old_text,sizeof(old_text))==ESP_OK);
  }
  if(kind==2){nvs::Page page;require(page.load(&baseline,0)==ESP_OK);require(page.writeItem(ns,nvs::ItemType::BLOB,"key",old_blob.data(),old_blob.size())==ESP_OK);}
  for(unsigned cut=0;cut<40;++cut){Memory m=baseline;m.fail_after=cut;esp_err_t write_result=ESP_OK;
   {nvs::Storage store(&m);require(store.init(0,32)==ESP_OK);require(store.createOrOpenNamespace("ecu_engine",false,ns)==ESP_OK);
    if(kind==0)write_result=store.writeItem(ns,nvs::ItemType::U32,"key",&new_scalar,sizeof(new_scalar));
    if(kind==1)write_result=store.writeItem(ns,nvs::ItemType::SZ,"key",new_text,sizeof(new_text));
    if(kind==2)write_result=store.writeItem(ns,nvs::ItemType::BLOB,"key",new_blob.data(),new_blob.size());
   }
   m.fail_after=-1;{nvs::Storage store(&m);require(store.init(0,32)==ESP_OK);require(store.createOrOpenNamespace("ecu_engine",false,ns)==ESP_OK);size_t size=0;
    const auto type=kind==0?nvs::ItemType::U32:kind==1?nvs::ItemType::SZ:nvs::ItemType::BLOB;
    if(kind==0)size=sizeof(old_scalar);else require(store.getItemDataSize(ns,type,"key",size)==ESP_OK);std::vector<unsigned char> value(size);require(store.readItem(ns,type,"key",value.data(),size)==ESP_OK);
    const bool old=kind==0?(size==sizeof(old_scalar)&&!std::memcmp(value.data(),&old_scalar,size)):kind==1?(size==sizeof(old_text)&&!std::memcmp(value.data(),old_text,size)):value==old_blob;
    const bool current=kind==0?(size==sizeof(new_scalar)&&!std::memcmp(value.data(),&new_scalar,size)):kind==1?(size==sizeof(new_text)&&!std::memcmp(value.data(),new_text,size)):value==new_blob;
    require(old||current);require(write_result!=ESP_OK||current);if(ledger)std::fprintf(ledger,"{\"kind\":%u,\"cut\":%u,\"write_result\":%d,\"value\":\"%s\"}\n",kind,cut,write_result,current?"new":"old");old_count+=old;new_count+=current;++trials;
   }
  }
 }
 if(ledger)std::fclose(ledger);
 std::cout<<"{\"passed\":true,\"trials\":"<<trials<<",\"old\":"<<old_count<<",\"new\":"<<new_count<<",\"assertions\":"<<checks<<"}\n";
}
