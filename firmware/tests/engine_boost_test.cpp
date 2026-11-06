#include "ecu/engine_json.hpp"
#include "ecu/boost_command.hpp"
#include "ecu/boost_runtime_json.hpp"
#include "ecu/tuning_document.hpp"
#include "ecu/engine_data.hpp"
#include <cassert>
#include <fstream>
#include <iostream>
#include <iterator>
using namespace ecu;
#define check(expression) verify(bool(expression),#expression,__LINE__)
int main(int argc,char**argv){
 unsigned checks=0;auto verify=[&](bool good,const char*expression,unsigned line){++checks;if(!good)std::cerr<<"line "<<line<<" check "<<checks<<": "<<expression<<"\n";assert(good);};
 engine::Tune t;t.injector_cc_min=600;t.afterstart_pct=0;t.dfco_enabled=false;t.boost_control.pressure_enabled=true;
 t.boost_control.mode=boost::Mode::OpenLoop;t.boost_control.open_duty.cells.fill(40);
 engine::Inputs in;in.rpm=2000;in.map_kpa=150;in.tps_pct=50;in.clt_c=85;in.iat_c=25;in.battery_v=14;in.sensor_v=5;in.synced=in.phase_synced=in.sensors_valid=true;
 check(!engine::validate(t));check(engine::input_requirements(t).map);
 for(auto strategy:{engine::Strategy::BatchWasted,engine::Strategy::Sequential,engine::Strategy::SemiSequential}){
  t.strategy=strategy;engine::Controller controller;engine::Output out;
  for(unsigned n=0;n<=100;++n){in.sampled_us=n*5000;out=controller.step(t,in,in.sampled_us);check(!out.faults);}
  check(out.pulse_ms>0&&!out.fuel_cut&&!out.spark_cut&&out.boost_control.duty_pct==40);
  in.map_kpa=230;in.sampled_us=505000;out=controller.step(t,in,in.sampled_us);
  check(out.faults&engine::Overboost);check(out.fuel_cut&&out.spark_cut&&!out.pulse_ms&&!out.dwell_ms&&!out.pump);
  check(out.boost_control.inhibit_engine&&!out.boost_control.duty_pct&&!out.cylinder_data);
  in.map_kpa=200;
  for(unsigned n=102;n<152;++n){in.sampled_us=n*5000;out=controller.step(t,in,in.sampled_us);check(out.fuel_cut&&out.spark_cut);}
  in.sampled_us=760000;out=controller.step(t,in,in.sampled_us);check(!out.faults&&!out.fuel_cut&&!out.spark_cut);
  in.map_qualified=false;in.sampled_us=765000;out=controller.step(t,in,in.sampled_us);check(out.faults&engine::BadSensor);check(out.boost_control.duty_pct==0);
  in.map_qualified=true;in.map_kpa=150;
 }
 t.strategy=engine::Strategy::BatchWasted;t.boost_control.mode=boost::Mode::ClosedLoop;
 t.load_model.baro_source=load::BaroSource::Aux;check(engine::validate(t)!=nullptr);
 t.load_model.aux_role=load::AuxRole::Baro;check(!engine::validate(t));check(engine::input_requirements(t).baro);
 t.load_model.baro_source=load::BaroSource::Fixed;check(!engine::validate(t));
 t.secondary_tables.fuel.mode=secondary::Mode::Conditional;t.secondary_tables.fuel.condition=secondary::Condition::Map;t.secondary_tables.fuel.threshold=180;
 check(!engine::validate(t));
 // Input-mode switch qualification keeps the same pressure context even
 // while its stored MAP condition is inactive in this mode.
 t.secondary_tables.fuel.mode=secondary::Mode::Input;
 in.table_switches[0].source=secondary::InputSource::Synthetic;in.table_switches[0].valid=true;
 engine::Controller switched;in.sampled_us=0;
 for(unsigned n=0;n<=12;++n){in.sampled_us=n*5000;in.table_switches[0].observed_us=in.sampled_us;switched.step(t,in,in.sampled_us);}
 in.sampled_us=65000;in.table_switches[0].observed_us=in.sampled_us;auto switched_out=switched.step(t,in,in.sampled_us);check(!switched_out.faults&&switched_out.secondary_fuel.input_qualified);
 t.boost_control=boost::Config{};check(engine::validate(t)!=nullptr); //180kPa secondary threshold cannot hide in NA mode.
 t.secondary_tables={};check(!engine::validate(t));engine::Controller na;in.map_kpa=150;in.sampled_us=0;
 auto out=na.step(t,in,0);check(out.faults&engine::BadSensor);check(out.fuel_cut&&out.spark_cut);
 // Saturated unclamped PID demand is diagnostic data, not an invalid duty.
 engine::Tune forced;forced.injector_cc_min=600;forced.boost_control.pressure_enabled=true;forced.boost_control.mode=boost::Mode::ClosedLoop;forced.boost_control.kp=10;forced.boost_control.cut_kpa=250;
 for(double map:{100.,220.}){engine::Controller controller;in.map_kpa=map;in.sampled_us=0;auto saturated=controller.step(forced,in,0);check(!saturated.faults);auto record=boost::record(saturated.boost_control,forced.boost_control);check(boost::valid_record(record));auto*j=boost::record_json(record);boost::Record parsed_record;check(j&&boost::parse_record(j,parsed_record,true));cJSON_Delete(j);check(parsed_record.values[1]==(map==100?500:-700));}
 forced.boost_control.slew_pct_s=2000;forced.boost_control.mode=boost::Mode::OpenLoop;forced.boost_control.open_duty.cells.fill(40);engine::Controller controller;in.map_kpa=150;in.sampled_us=1000;auto proposal=controller.step(forced,in,1000);check(!proposal.faults);in.sampled_us=21000;proposal=controller.step(forced,in,21000);check(proposal.boost_control.duty_pct==40);
 timing::Command command;command.output=proposal;command.sequence=1;command.command_us=command.sampled_us=21000;command.tune_revision=command.sensor_revision=1;boost::prepare_pwm(command,forced);check(command.boost_period_us==40000&&command.boost_high_us==16000);
 timing::TimingStats stats;auto request=boost::pwm_command(command,command,21000,stats);check(request.enabled&&request.high_us==16000);
 check(!boost::pwm_command(command,command,21000,stats,false,false).enabled);
 auto data=engine::synthetic_data(forced,in,proposal,1,21000);check(data.input_valid&(1U<<engine::MapKpa));check(data.boost_control.available&&data.boost_control.mode==1);
 tuning::Page wire;tuning::encode_page(forced,1,wire);engine::Tune decoded;check(tuning::decode_page(wire,1,decoded));check(decoded.boost_control.open_duty.cells[17]==40&&decoded.boost_control.pressure_enabled);
 in.map_kpa=450;in.sensors_valid=false;in.sampled_us=26000;proposal=controller.step(forced,in,26000);check((proposal.faults&engine::Overboost)&&(proposal.faults&engine::BadSensor));check(proposal.boost_control.inhibit_engine);in.sensors_valid=true;
 std::ifstream file(std::string(argc>1?argv[1]:".")+"/config/engine/defaults-v9.json");std::string legacy((std::istreambuf_iterator<char>(file)),{}),canonical;
 check(!legacy.empty());engine::Tune parsed;check(engine::canonical_tune(legacy.c_str(),parsed,canonical));
 auto*j=cJSON_Parse(canonical.c_str());check(j&&cJSON_GetObjectItemCaseSensitive(j,"schema_version")->valueint==11);
 check(!parsed.boost_control.pressure_enabled&&parsed.boost_control.mode==boost::Mode::Off);
 auto*boost=cJSON_GetObjectItemCaseSensitive(j,"boost_control");check(boost&&cJSON_GetArraySize(cJSON_GetObjectItemCaseSensitive(cJSON_GetObjectItemCaseSensitive(boost,"target"),"cells"))==64);
 cJSON_SetNumberValue(cJSON_GetObjectItemCaseSensitive(j,"schema_version"),9);check(!engine::parse_tune(j,parsed));
 cJSON_SetNumberValue(cJSON_GetObjectItemCaseSensitive(j,"schema_version"),10);cJSON_DeleteItemFromObject(j,"boost_control");check(!engine::parse_tune(j,parsed));cJSON_Delete(j);
 std::cout<<"Integrated engine boost and migration: "<<checks<<" assertions passed; physical outputs inhibited\n";
}
