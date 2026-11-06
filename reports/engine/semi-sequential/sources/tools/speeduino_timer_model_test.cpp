// Exercise the actual deterministic HAL with its generated16bit timer header.
#include "SoftwareTimer.h"
#include <cassert>
#include <cstdint>
#include <iostream>
extern "C" void speeduino_sim_advance(std::uint64_t);
extern "C" std::uint64_t speeduino_sim_micros();
extern "C" void speeduino_sim_observe(){}
void oneMSInterval(){}
int main(){
 static_assert(sizeof(software_timer_t::counter_t)==2,"Expected16bit timer");
 static_assert(software_timer_t::ticksToMicros(UINT16_MAX)==262140,"Mega-like period");
 software_timer_t timer;unsigned hits=0;timer.setCallback([&](){++hits;timer.disableTimer();});
 speeduino_sim_advance(262136);assert(timer.counter==65534&&hits==0);
 timer.compare=1;timer.enableTimer();speeduino_sim_advance(262144);assert(timer.counter==0&&hits==0);
 speeduino_sim_advance(262148);assert(hits==1&&timer.counter==1);
 // A compare behind the current count must wait for wrap, never fire at>=.
 speeduino_sim_advance(262184);timer.compare=5;timer.enableTimer();speeduino_sim_advance(262188);assert(hits==1);
 speeduino_sim_advance(524308);assert(hits==2&&timer.counter==5);
 // Zero-tick delay cannot match retroactively. It takes a complete wrap.
 timer.compare=timer.counter.load();timer.enableTimer();speeduino_sim_advance(524312);assert(hits==2);
 speeduino_sim_advance(786452);assert(hits==3&&timer.counter==5);
 // Count while disabled; ignore compare matches rather than latch a fakeIRQ.
 timer.compare=6;speeduino_sim_advance(786456);assert(hits==3&&timer.counter==6);
 timer.enableTimer();speeduino_sim_advance(786460);assert(hits==3);
 speeduino_sim_advance(1048600);assert(hits==4&&timer.counter==6);
 std::cout<<"16bit timer wrap, compare equality, zero-tick delay and disabled/re-enable tests passed\n";
}
