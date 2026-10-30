#pragma once
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
namespace ecu::config {
constexpr unsigned kSensors=6, kPoints=16;
enum class Mode { Voltage, Linear, Table, Ntc };
struct Point { double v{}, value{}; };
struct Sensor {
 char id[16]{},label[64]{},unit[16]{};Mode mode{Mode::Voltage};bool confirmed{},pullup_fitted{};
 double fault_low_v{.02},fault_high_v{5.15},filter_ms{100},v0{.5},y0{},v1{4.5},y1{100};
 double ntc_r0_ohm{10000},ntc_t0_c{25},ntc_beta_k{3950},pullup_ohm{2490};
 unsigned point_count{2};std::array<Point,kPoints> points{};
};
struct Config {std::uint32_t revision{1};char name[64]{"ECU bench profile"};double adc_reference_v{3.3};unsigned ui_poll_ms{500},slots{60},missing{2},max_rpm{8000};std::array<Sensor,kSensors> sensors{};};
inline bool finite(double x){return std::isfinite(x);}
inline bool valid(const Config& c){
 if (!finite(c.adc_reference_v)||c.adc_reference_v<2.9||c.adc_reference_v>3.6||c.ui_poll_ms<100||c.ui_poll_ms>2000||c.slots<12||c.slots>120||c.missing<1||c.missing>3||c.missing>=c.slots/4||c.max_rpm<500||c.max_rpm>12000)return false;
 const char* ids[]={"map","tps","clt","iat","wideband","postcat"};
 for(unsigned i=0;i<kSensors;++i){const auto&s=c.sensors[i];
  if(std::strcmp(s.id,ids[i])||!s.label[0]||!s.unit[0]||!finite(s.fault_low_v)||!finite(s.fault_high_v)||s.fault_low_v<0||s.fault_high_v>5.3||s.fault_low_v>=s.fault_high_v||!finite(s.filter_ms)||s.filter_ms<0||s.filter_ms>2000)return false;
  if(!finite(s.v0)||!finite(s.v1)||s.v0<0||s.v1>5.3||s.v1-s.v0<.01||!finite(s.y0)||!finite(s.y1)||std::abs(s.y0)>100000||std::abs(s.y1)>100000)return false;
  if(s.point_count<2||s.point_count>kPoints)return false;
  for(unsigned p=0;p<s.point_count;++p)if(!finite(s.points[p].v)||!finite(s.points[p].value)||s.points[p].v<0||s.points[p].v>5.3||std::abs(s.points[p].value)>100000||(p&&s.points[p].v-s.points[p-1].v<.001))return false;
  if(!finite(s.ntc_r0_ohm)||s.ntc_r0_ohm<100||s.ntc_r0_ohm>1000000||!finite(s.ntc_t0_c)||s.ntc_t0_c< -50||s.ntc_t0_c>150||!finite(s.ntc_beta_k)||s.ntc_beta_k<1000||s.ntc_beta_k>10000||!finite(s.pullup_ohm)||s.pullup_ohm<100||s.pullup_ohm>100000)return false;
  if(s.mode==Mode::Ntc&&(!(i==2||i==3)||!s.pullup_fitted))return false;
 }
 return true;
}
struct Reading {double value{},sensor_v{},adc_v{};bool valid{};const char* fault{"waiting"};};
inline Reading convert(const Sensor&s,double sensor_v,double adc_v,double supply){
 Reading r{};r.sensor_v=sensor_v;r.adc_v=adc_v;
 if(!finite(sensor_v)||!finite(adc_v)){r.fault="invalid sample";return r;}
 if(sensor_v<s.fault_low_v){r.fault="below input range";return r;}if(sensor_v>s.fault_high_v){r.fault="above input range";return r;}
 if(s.mode==Mode::Voltage)r.value=sensor_v;
 else if(s.mode==Mode::Linear){if(sensor_v<s.v0||sensor_v>s.v1){r.fault="outside calibration";return r;}r.value=s.y0+(sensor_v-s.v0)*(s.y1-s.y0)/(s.v1-s.v0);}
 else if(s.mode==Mode::Table){
  if(sensor_v<s.points[0].v||sensor_v>s.points[s.point_count-1].v){r.fault="outside calibration";return r;}
  unsigned p=1;while(p<s.point_count-1&&sensor_v>s.points[p].v)++p;
  const auto&a=s.points[p-1];const auto&b=s.points[p];r.value=a.value+(sensor_v-a.v)*(b.value-a.value)/(b.v-a.v);
 }else{
  if(!s.pullup_fitted){r.fault="pull-up not confirmed";return r;}
  if(!finite(supply)||supply<4||supply>5.3||sensor_v<=.001||sensor_v>=supply){r.fault="supply / NTC wiring";return r;}
  const double req=s.pullup_ohm*sensor_v/(supply-sensor_v);
  const double inv=1/req-1/55000.0; // The board's 22k + 33k divider loads the sensor.
  if(inv<=0){r.fault="NTC open / wrong pull-up";return r;}
  const double resistance=1/inv, kelvin=1/(1/(s.ntc_t0_c+273.15)+std::log(resistance/s.ntc_r0_ohm)/s.ntc_beta_k);
  r.value=kelvin-273.15;
  if(!finite(r.value)||r.value< -80||r.value>250){r.fault="NTC curve / open circuit";return r;}
 }
 r.valid=finite(r.value);r.fault=r.valid?"ok":"invalid conversion";return r;
}
}
