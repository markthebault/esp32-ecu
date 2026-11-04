#pragma once
#include <mutex>
using SemaphoreHandle_t=std::mutex*;
inline std::mutex log_test_mutex;
inline SemaphoreHandle_t xSemaphoreCreateMutex(){return &log_test_mutex;}
inline int xSemaphoreTake(SemaphoreHandle_t mutex,unsigned wait){if(!wait)return mutex->try_lock()?1:0;mutex->lock();return 1;}
inline void xSemaphoreGive(SemaphoreHandle_t mutex){mutex->unlock();}
