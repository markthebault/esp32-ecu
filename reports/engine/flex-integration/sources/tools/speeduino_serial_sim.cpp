// Serial-only native positive control. The default numerical adapter is intact.
// No physical serial/GPIO devices are opened. Genuine production setup/loop
// and serial commands execute; this is not an engine timing/plant benchmark.
#define main numerical_benchmark_main
#include "speeduino_sim.cpp"
#undef main
#include <atomic>
#include <chrono>
#include <deque>
#include <iomanip>
#include <mutex>
#include <thread>
#include <streambuf>

namespace serial_fixture {
constexpr size_t capacity=16384;
std::deque<uint8_t> rx,tx;
std::mutex io_mutex,output_mutex;
std::atomic<bool> running{true};
std::atomic<uint64_t> loops{0},received{0},transmitted{0};
std::chrono::steady_clock::time_point epoch;
uint64_t base_us=0;
void isolate_coverage(){
 char binary[PATH_MAX];const auto n=readlink("/proc/self/exe",binary,sizeof(binary)-1);
 if(n<=0)throw std::runtime_error("cannot locate serial fixture executable");
 binary[n]='\0';const std::string path(binary);const auto directory=path.substr(0,path.find_last_of('/'));
 if(setenv("GCOV_PREFIX",(directory+"/gcov").c_str(),1))throw std::runtime_error("cannot isolate native coverage records");
}
uint64_t wall_us(){return base_us+uint64_t(std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now()-epoch).count());}
void output(const std::string&line){std::lock_guard<std::mutex>lock(output_mutex);std::cout<<line<<'\n'<<std::flush;}
class TxBuffer:public std::streambuf {
 std::streamsize xsputn(const char*p,std::streamsize n)override{
  std::lock_guard<std::mutex>lock(io_mutex);
  if(n<0||size_t(n)>capacity-tx.size())throw std::runtime_error("serial fixture TX capacity");
  for(std::streamsize i=0;i<n;++i)tx.push_back(uint8_t(p[i]));return n;
 }
 int_type overflow(int_type ch)override{if(traits_type::eq_int_type(ch,traits_type::eof()))return traits_type::not_eof(ch);const char value=traits_type::to_char_type(ch);xsputn(&value,1);return ch;}
};
void install_serial(){
 using namespace fakeit;auto&mock=SimpleArduinoFake::getContext()._Serial;
 When(Method(mock,available)).AlwaysDo([](){std::lock_guard<std::mutex>lock(io_mutex);return int(rx.size());});
 When(Method(mock,peek)).AlwaysDo([](){std::lock_guard<std::mutex>lock(io_mutex);return rx.empty()?-1:int(rx.front());});
 When(Method(mock,read)).AlwaysDo([](){std::lock_guard<std::mutex>lock(io_mutex);if(rx.empty())return-1;const int c=rx.front();rx.pop_front();return c;});
 When(Method(mock,availableForWrite)).AlwaysDo([](){std::lock_guard<std::mutex>lock(io_mutex);return int(std::min<size_t>(64,capacity-tx.size()));});
 // All inherited Print/write overloads retain the TX-backed ostream installed
 // by fakeMega, including the genuine legacy raw-F print implementation.
}
void drain(){
 std::deque<uint8_t>bytes;{std::lock_guard<std::mutex>lock(io_mutex);bytes.swap(tx);}
 if(bytes.empty())return;std::ostringstream line;line<<"tx "<<wall_us()<<' '<<std::hex<<std::setfill('0');
 for(auto c:bytes)line<<std::setw(2)<<unsigned(c);transmitted+=bytes.size();output(line.str());
}
void worker(){
 try{
  while(running){speeduino_sim_advance(wall_us());run_loop();++loops;drain();std::this_thread::sleep_for(std::chrono::milliseconds(1));}
  drain();
 }catch(const std::exception&e){output(std::string("error ")+e.what());running=false;}
}
int nibble(char c){return c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:c>='A'&&c<='F'?c-'A'+10:-1;}
}
int main(){
 using namespace serial_fixture;TxBuffer buffer;std::ostream serial_output(&buffer);serial_output.exceptions(std::ios::badbit);std::istringstream serial_input;std::thread ecu;
 try{
  isolate_coverage();
  fakeMega(serial_output,serial_input);prepare_hal();install_serial();configure();
  setPinMapping(3);set_sensors(100,0,85,25,14,14.7);setup();set_sensors(100,0,85,25,14,14.7);
  base_us=speeduino_sim_micros();epoch=std::chrono::steady_clock::now();
  using namespace fakeit;auto&functions=SimpleArduinoFake::getContext()._Function;
  When(Method(functions,micros)).AlwaysDo([]()->unsigned long{return uint32_t(wall_us());});
  When(Method(functions,millis)).AlwaysDo([]()->unsigned long{return uint32_t(wall_us()/1000);});
  When(Method(functions,delay)).AlwaysDo([](unsigned long n){std::this_thread::sleep_for(std::chrono::milliseconds(n));});
  When(Method(functions,delayMicroseconds)).AlwaysDo([](unsigned n){std::this_thread::sleep_for(std::chrono::microseconds(n));});
  output("ready serial-only production loop; virtual pins; wall-clock receive deadlines");ecu=std::thread(worker);
  std::string line;
  while(running&&std::getline(std::cin,line)){
   if(line=="quit")break;
   if(line=="stats"){output("stats "+std::to_string(loops.load())+' '+std::to_string(received.load())+' '+std::to_string(transmitted.load()));continue;}
   if(line.compare(0,3,"rx ")||line.size()<5||(line.size()-3)%2||(line.size()-3)/2>capacity)throw std::runtime_error("invalid serial fixture injection");
   std::deque<uint8_t>bytes;
   for(size_t i=3;i<line.size();i+=2){const auto a=nibble(line[i]),b=nibble(line[i+1]);if(a<0||b<0)throw std::runtime_error("invalid serial hex");bytes.push_back(uint8_t(16*a+b));}
   std::lock_guard<std::mutex>lock(io_mutex);if(bytes.size()>capacity-rx.size())throw std::runtime_error("serial fixture RX capacity");
   received+=bytes.size();rx.insert(rx.end(),bytes.begin(),bytes.end());
  }
  running=false;if(ecu.joinable())ecu.join();return 0;
 }catch(const std::exception&e){running=false;if(ecu.joinable())ecu.join();std::cerr<<"serial fixture failed: "<<e.what()<<'\n';return 1;}
}
