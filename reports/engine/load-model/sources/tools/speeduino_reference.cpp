// Adapter only. Production calculations are linked from the external, pinned
// GPL-2.0 Speeduino checkout; no reimplementation is presented as a reference.
#include "fuel_calcs.h"
#include "globals.h"
#include <iostream>
#include <array>
#include "FakeMega.h"
#include <sstream>
static std::stringstream reference_serial;
extern "C" void setUp() {fakeMega(reference_serial,reference_serial);}
extern "C" void tearDown() {}
struct ReferenceSetup {ReferenceSetup(){setUp();}} reference_setup __attribute__((init_priority(65534)));
int main(){
 unsigned req,ve,map,corrections,dead_us,rpm;
 while(std::cin>>req>>ve>>map>>corrections>>dead_us>>rpm){
  if(req>255||ve>255||map>110||corrections>1000||dead_us>3000||rpm<50||rpm>8000)return 2;
  config2 a{};config6 b{};config10 d{};statuses s{};
  a.reqFuel=req;a.injOpen=(dead_us+50)/100;a.strokes=FOUR_STROKE;a.multiplyMAP=MULTIPLY_MAP_MODE_100;a.dutyLim=85;a.includeAFR=false;a.incorporateAFR=false;
  s.injLayout=INJ_PAIRED;s.nSquirts=2;s.RPM=rpm;s.revolutionTime=60000000UL/rpm;s.VE=ve;s.MAP=map;s.corrections=corrections;s.batCorrection=100;s.nitrous_status=NITROUS_OFF;s.rotationStatus=EngineRotationStatus::Running;
  const auto pw=computePulseWidths(a,b,d,s);std::cout<<pw.primary<<' '<<pw.secondary<<'\n';
 }
}
