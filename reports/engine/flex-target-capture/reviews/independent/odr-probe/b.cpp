#include "ecu/flex_capture_owner.hpp"
extern bool compare_a();
int main(){return compare_a()&&!ecu::flex::same(ecu::flex::CaptureVersion{1,2,3,true},ecu::flex::CaptureVersion{1,2,4,true})?0:1;}
