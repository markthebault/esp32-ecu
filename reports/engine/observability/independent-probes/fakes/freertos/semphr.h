#pragma once
#include "FreeRTOS.h"
#include <mutex>
using SemaphoreHandle_t=std::mutex*;
extern std::mutex* review_mutex;
inline SemaphoreHandle_t xSemaphoreCreateMutex(){return review_mutex=new std::mutex;}
inline int xSemaphoreTake(SemaphoreHandle_t mutex,std::uint32_t ticks){if(!ticks)return mutex->try_lock()?pdTRUE:pdFALSE;mutex->lock();return pdTRUE;}
inline int xSemaphoreGive(SemaphoreHandle_t mutex){mutex->unlock();return pdTRUE;}
