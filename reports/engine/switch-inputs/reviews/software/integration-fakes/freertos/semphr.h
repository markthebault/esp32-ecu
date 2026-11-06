#pragma once
#include "freertos/FreeRTOS.h"
using SemaphoreHandle_t=std::mutex*;
inline std::mutex reviewer_engine_mutex;
inline bool reviewer_force_busy=false;
inline SemaphoreHandle_t xSemaphoreCreateMutex(){return &reviewer_engine_mutex;}
inline int xSemaphoreTake(SemaphoreHandle_t m,unsigned wait){if(!wait)return reviewer_force_busy?0:(m->try_lock()?1:0);m->lock();return 1;}
inline void xSemaphoreGive(SemaphoreHandle_t m){m->unlock();}
