#pragma once
#include "ecu/engine_log.hpp"

namespace ecu::engine_log_service {
void init();
// Producer never waits for HTTP/export work. No JSON or flash writes here.
void observe(const engine::RuntimeSample&);
const char* boot_id();
bool same_boot(const char*);
engine_log::Header header();
std::uint32_t contention_attempts();
bool exporting();
bool start(unsigned period_ms, unsigned duration_s);
bool stop(std::uint32_t log_id);
void page(std::uint32_t log_id, std::uint32_t after, engine_log::Page&);
// A stopped ring is held against rearming for a streamed retained-window export.
bool begin_export(std::uint32_t log_id, engine_log::Header&);
bool export_row(std::uint32_t log_id, std::uint32_t sequence, engine_log::Row&);
void end_export();
}
