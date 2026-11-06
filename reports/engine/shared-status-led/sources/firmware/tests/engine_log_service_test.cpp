// Compile the actual task service with mutex/clock fixtures, no ESP peripherals.
#include "ecu/engine_log_service.hpp"
#include "ecu/engine_target.hpp"
#include "freertos/semphr.h"
#include <atomic>
#include <cassert>
#include <iostream>
#include <thread>

std::atomic<std::uint64_t> simulated_clock{0};
namespace ecu::engine_target {std::uint64_t clock_us(){return simulated_clock.load();}}
using namespace ecu;
int main(){
 engine_log_service::init();assert(std::strlen(engine_log_service::boot_id())==32);
 assert(engine_log_service::same_boot(engine_log_service::boot_id()));assert(!engine_log_service::same_boot("old"));
 assert(engine_log_service::start(20,1));assert(!engine_log_service::start(100,1));
 engine::RuntimeSample sample;sample.sequence=1;sample.flags=engine::Present;sample.source=engine::DataSource::Target;
 engine_log_service::observe(sample);assert(engine_log_service::header().total==1);
 log_test_mutex.lock();engine_log_service::observe(sample);log_test_mutex.unlock();
 assert(engine_log_service::contention_attempts()==1);
 simulated_clock=1000000;const auto frozen=engine_log_service::header();
 assert(frozen.state==engine_log::State::Timeout&&frozen.missed_periods==49&&frozen.total==1);
 engine_log::Header exported;assert(engine_log_service::begin_export(frozen.log_id,exported));assert(engine_log_service::exporting());
 std::atomic<bool> start_succeeded{true};
 std::thread competing_start([&]{start_succeeded=engine_log_service::start(100,1);});competing_start.join();assert(!start_succeeded);
 engine_log::Row row;assert(engine_log_service::export_row(frozen.log_id,1,row));assert(row.sample.sequence==1);
 assert(!engine_log_service::begin_export(frozen.log_id,exported));assert(!engine_log_service::export_row(frozen.log_id+1,1,row));
 engine_log_service::end_export();assert(!engine_log_service::exporting());assert(!engine_log_service::export_row(frozen.log_id,1,row));
 assert(engine_log_service::start(100,1));assert(!engine_log_service::stop(frozen.log_id));
 engine_log::Page old;engine_log_service::page(frozen.log_id,0,old);assert(old.superseded);
 sample.sequence=2;sample.control_us=sample.sampled_us=1000000;engine_log_service::observe(sample);
 simulated_clock=1500000;assert(engine_log_service::stop(frozen.log_id+1));assert(engine_log_service::header().missed_periods==5);
 std::cout<<"Actual task logger: timeout accounting, contention, export lease and session races passed\n";
}
