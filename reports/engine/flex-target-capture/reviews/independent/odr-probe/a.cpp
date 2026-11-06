#include "ecu/flex_capture_owner.hpp"
bool compare_a(){return ecu::flex::same(ecu::flex::CaptureVersion{1,2,3,true},ecu::flex::CaptureVersion{1,2,3,true});}
