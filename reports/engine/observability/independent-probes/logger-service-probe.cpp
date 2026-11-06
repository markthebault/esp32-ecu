#include "ecu/engine_log_service.hpp"
#include <atomic>
#include <chrono>
#include <thread>
#include <mutex>
#include <cassert>
#include <iostream>
std::mutex* review_mutex=nullptr;
static std::atomic<std::uint64_t> review_now{0};
namespace ecu::engine_target {std::uint64_t clock_us(){return review_now.load();}}
ecu::engine::RuntimeSample point(unsigned n){ecu::engine::RuntimeSample r;r.sequence=n;r.source=ecu::engine::DataSource::Target;r.flags=ecu::engine::Present;r.control_us=r.sampled_us=review_now.load();return r;}
int main(){using namespace ecu;engine_log_service::init();const std::string boot=engine_log_service::boot_id();assert(boot.size()==32&&engine_log_service::same_boot(boot.c_str())&&!engine_log_service::same_boot("old"));assert(engine_log_service::start(100,1));engine_log_service::observe(point(1));const auto id=engine_log_service::header().log_id;engine_log::Header frozen;assert(!engine_log_service::begin_export(id,frozen));
 review_mutex->lock();review_now=100000;std::atomic<bool> returned{false};std::thread producer([&]{engine_log_service::observe(point(2));returned=true;});for(unsigned n=0;n<100&&!returned;++n)std::this_thread::sleep_for(std::chrono::milliseconds(1));const bool nonblocking=returned.load();review_mutex->unlock();producer.join();assert(nonblocking&&engine_log_service::contention_attempts()==1);
 review_now=200000;engine_log_service::observe(point(3));const auto h=engine_log_service::header();assert(h.total==2&&h.missed_periods==1);assert(!engine_log_service::stop(id+1));assert(engine_log_service::stop(id));assert(engine_log_service::begin_export(id,frozen));assert(!engine_log_service::start(20,1)&&!engine_log_service::begin_export(id,frozen));engine_log::Row row;assert(engine_log_service::export_row(id,1,row)&&row.sample.sequence==1);assert(engine_log_service::export_row(id,2,row)&&row.sample.sequence==3);
 engine_log::Page copied;engine_log_service::page(id,0,copied);assert(copied.count==2);engine_log_service::end_export();assert(engine_log_service::start(20,1));assert(!engine_log_service::stop(id));engine_log::Page stale;engine_log_service::page(id,0,stale);assert(stale.superseded&&copied.header.log_id==id&&copied.rows[1].sample.sequence==3);
 delete review_mutex;review_mutex=nullptr;std::cout<<"{\"boot_guards_passed\":true,\"producer_returns_while_reader_mutex_is_held\":true,\"contention_count\":1,\"missed_period_after_contention\":1,\"lease_blocks_rearm\":true,\"lease_rows_remain_stable\":true,\"stale_stop_rejected\":true,\"copied_page_survives_new_log\":true}\n";
}
