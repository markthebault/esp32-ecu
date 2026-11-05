#include "nvs_storage.hpp"
#include "spi_flash_mmap.h"
#include <vector>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <iostream>
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
 std::cout.setf(std::ios::unitbuf);
 for(unsigned size:{49152U,53248U,57344U,60000U}){
  Memory m;unsigned saves=0;nvs_stats_t stats{};
  for(unsigned block=0;block<10;++block){
   nvs::Storage s(&m);require(s.init(0,32)==ESP_OK);uint8_t ns=0;require(s.createOrOpenNamespace("ecu_engine",true,ns)==ESP_OK);
   for(unsigned j=0;j<20;++j){auto v=data(size,block*20+j);auto rc=s.writeItem(ns,nvs::ItemType::BLOB,"tune",v.data(),v.size());
    if(rc!=ESP_OK){std::cout<<"size="<<size<<" save="<<saves<<" error="<<rc<<"\n";break;}
    ++saves;std::vector<unsigned char> recovered(size);require(s.readItem(ns,nvs::ItemType::BLOB,"tune",recovered.data(),recovered.size())==ESP_OK);require(v==recovered);require(s.fillStats(stats)==ESP_OK);
   }
  }
  std::cout<<"size="<<size<<" saves="<<saves<<" writes="<<m.writes<<" erases="<<m.erases<<" used_entries="<<stats.used_entries<<" available_entries="<<stats.available_entries<<"\n";
 }
 // Inject failure before each low-level operation of one changed max-size update.
 Memory baseline;const auto previous=data(49152,22),next=data(49152,23);
 {nvs::Storage s(&baseline);require(s.init(0,32)==ESP_OK);uint8_t ns;require(s.createOrOpenNamespace("ecu_engine",true,ns)==ESP_OK);require(s.writeItem(ns,nvs::ItemType::BLOB,"tune",previous.data(),previous.size())==ESP_OK);}
 unsigned failures=0,old_after=0,new_after=0,lost=0,acknowledged_loss=0;
 for(unsigned cut=0;cut<360;++cut){Memory m=baseline;m.fail_after=cut;esp_err_t write_result=ESP_FAIL;
  {nvs::Storage s(&m);require(s.init(0,32)==ESP_OK);uint8_t ns;require(s.createOrOpenNamespace("ecu_engine",false,ns)==ESP_OK);write_result=s.writeItem(ns,nvs::ItemType::BLOB,"tune",next.data(),next.size());if(write_result!=ESP_OK)++failures;}
  m.fail_after=-1;{nvs::Storage s(&m);require(s.init(0,32)==ESP_OK);uint8_t ns;require(s.createOrOpenNamespace("ecu_engine",false,ns)==ESP_OK);std::vector<unsigned char> recovered(previous.size());auto read=s.readItem(ns,nvs::ItemType::BLOB,"tune",recovered.data(),recovered.size());if(read!=ESP_OK||!(recovered==previous||recovered==next)){++lost;std::cout<<"cut="<<cut<<" read_error="<<read<<"\n";}else if(recovered==previous)++old_after;else++new_after;if(write_result==ESP_OK&&(read!=ESP_OK||recovered!=next))++acknowledged_loss;if(ledger)std::fprintf(ledger,"{\"cut\":%u,\"write_result\":%d,\"read_result\":%d,\"value\":\"%s\"}\n",cut,write_result,read,read!=ESP_OK?"unavailable":recovered==previous?"old":recovered==next?"new":"corrupt");}
 }
 std::cout<<"fault_trials=360 errors="<<failures<<" old_valid_after_reinit="<<old_after<<" new_valid_after_reinit="<<new_after<<" unavailable_after_reinit="<<lost<<" acknowledged_loss="<<acknowledged_loss<<" assertions="<<checks<<"\n";
 require(acknowledged_loss==0);if(ledger)require(std::fclose(ledger)==0);
}
