#include "globals.h"
#include "table2d.h"
#include "FakeMega.h"
#include <sstream>
#include <iostream>
std::stringstream& stream(){static auto* v=new std::stringstream;return *v;}
struct EarlySetup{EarlySetup(){fakeMega(stream(),stream());}};
EarlySetup early_setup __attribute__((init_priority(65534)));
extern "C" void speeduino_sim_observe(){}
int main(){
 uint8_t bins[6]={0,20,40,60,80,100},values[6]={100,110,120,130,140,150};
 table2D_u8_u8_6 table(&bins,&values);
 currentStatus.secl=0;
 std::cout<<"startup_input0="<<unsigned(table.getValue(0))<<"\n";
 currentStatus.secl=1;
 std::cout<<"after_second_input0="<<unsigned(table.getValue(0))<<"\n";
}
