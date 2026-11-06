#pragma once
// The upstream native Arduino fake has Mega GPIO numbers but Uno interrupt
// numbering. Use ArduinoCore-avr1.8.6's Mega mapping in this native HAL only.
// Production decoder/logger/scheduler source remains unchanged.
#include <Arduino.h>
#undef digitalPinToInterrupt
#define digitalPinToInterrupt(p) ((p)==2?0:((p)==3?1:((p)>=18&&(p)<=21?23-(p):NOT_AN_INTERRUPT)))
