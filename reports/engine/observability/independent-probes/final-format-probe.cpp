#include "ecu/engine_log_msl.hpp"
#include "ecu/engine_radio.hpp"
#include <cassert>
#include <cstring>
#include <cfloat>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
static std::vector<std::string> cells(const std::string& line){std::vector<std::string> v;std::istringstream s(line);std::string part;while(std::getline(s,part,'\t'))v.push_back(part);return v;}
int main(){using namespace ecu;engine_log::Header h;h.source=engine::DataSource::Target;h.log_id=h.period_ms=h.duration_s=h.total=h.retained=h.overwritten=h.missed_periods=h.repeated=h.invalid=UINT32_MAX;h.started_us=1;
engine_log::Row row;row.sample.source=engine::DataSource::Target;row.sample.flags=engine::Present;row.sample.sequence=UINT64_MAX;row.sample.worker_sequence=UINT64_MAX;row.sample.worker_observed_us=1;row.sample.control_us=row.sample.sampled_us=1;row.sample.input_valid=0xa5;row.sample.board_flags=15;row.sample.raw_adc.fill(UINT16_MAX);row.sample.inputs.fill(FLT_MAX);row.sample.proposals.fill(-FLT_MAX);row.recorded_us=UINT64_MAX;row.sequence=row.log_id=UINT32_MAX;
char text[2048];assert(engine_log::msl_header(h,text,sizeof text,"ffffffffffffffffffffffffffffffff"));const auto header_size=std::strlen(text);std::istringstream lines(text);std::string magic,meta,names,units;std::getline(lines,magic);std::getline(lines,meta);std::getline(lines,names);std::getline(lines,units);const auto names_cells=cells(names);assert(names_cells.size()==58&&cells(units).size()==58&&names_cells[27]=="InputValidMask");assert(engine_log::msl_row(h,row,text,sizeof text));const auto row_size=std::strlen(text);const auto row_cells=cells(text);assert(row_cells.size()==58&&row_cells[27]=="165");assert(!engine_log::msl_header(h,text,16)&&!engine_log::msl_row(h,row,text,16));
std::uint8_t bytes[radio::wire::engine_size];std::memset(bytes,0x5a,sizeof bytes);const auto original=std::string(reinterpret_cast<char*>(bytes),sizeof bytes);assert(!radio::wire::engine_body(bytes,row.sample,0,1,0,0,0,0));assert(std::string(reinterpret_cast<char*>(bytes),sizeof bytes)==original);assert(radio::wire::engine_body(bytes,row.sample,1,1,0,0,0,0));
std::cout<<"{\"msl_columns\":58,\"input_valid_mask_column\":27,\"input_valid_mask_value\":165,\"maximum_counter_header_bytes\":"<<header_size<<",\"stress_row_bytes\":"<<row_size<<",\"bounded_buffer_failures_rejected\":true,\"zero_session_rejected_without_writes\":true}\n";
}
