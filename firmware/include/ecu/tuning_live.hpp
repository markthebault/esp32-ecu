#pragma once
#include "ecu/tuning_layout.hpp"
#include "ecu/engine_data.hpp"
namespace ecu::tuning {
// Wire source codes retain own003's1=completed synthetic data;2=target.
// Input zeros with a clear validity bit mean unavailable, not a measurement.
inline void live_block(const engine::RuntimeSample&s,std::uint64_t now,std::array<std::uint8_t,live_bytes>&b){
 b.fill(0);const bool present=s.has(engine::Present)&&s.sequence;
 put_u32(b.data()+52,!s.has(engine::DummyPolicy));
 if(!present){put_u32(b.data()+64,UINT32_MAX);return;}
 auto value=[&](unsigned offset,float v){put_float(b.data()+offset,engine::finite(v)?v:0);};
 auto input=[&](unsigned offset,unsigned index){value(offset,(s.input_valid&(1U<<index))?s.inputs[index]:0);};
 value(0,float(s.control_us/1e6));value(4,s.proposals[engine::ProposalRpm]);input(8,engine::MapKpa);input(12,engine::TpsPct);input(16,engine::Lambda);
 for(auto pair:{std::pair<unsigned,unsigned>{20,engine::PulseMs},{24,engine::AdvanceDeg},{28,engine::DwellMs},{32,engine::VePct},{36,engine::TargetLambda},{40,engine::Ego}})value(pair.first,s.proposals[pair.second]);
 put_u32(b.data()+44,s.controller_faults);put_u32(b.data()+48,s.has(engine::CrankSynced)&&(!s.has(engine::PhaseRequired)||s.has(engine::PhaseSynced)));
 put_u32(b.data()+56,s.tune_revision);put_u32(b.data()+60,s.source==engine::DataSource::Target?2:s.source==engine::DataSource::Synthetic?1:0);
 const auto age=engine::data_age_us(s,s.control_us,now);put_u32(b.data()+64,engine::data_age_ms(age));put_u32(b.data()+68,s.source==engine::DataSource::Synthetic);put_u32(b.data()+72,1);
 put_u32(b.data()+76,s.has(engine::CrankSynced));put_u32(b.data()+80,s.has(engine::PhaseSynced));put_u32(b.data()+84,s.has(engine::PhaseRequired));put_u32(b.data()+88,s.phase_losses);put_u32(b.data()+92,s.strategy);put_u32(b.data()+96,s.cam_rejected);
 for(unsigned c=0;c<4;++c){const bool known=s.cylinder_valid&(1U<<c);value(100+c*16,known?s.cylinder_pulse_ms[c]:0);value(104+c*16,known?s.cylinder_advance_deg[c]:0);value(108+c*16,known?s.cylinder_fuel_pct[c]:0);value(112+c*16,known?s.cylinder_duty_pct[c]:0);}
 put_u32(b.data()+164,s.cylinder_valid);put_u32(b.data()+168,s.cylinder_enabled);put_u32(b.data()+172,s.cylinder_capacity_mask);put_u32(b.data()+176,s.cylinder_spark_clamp_mask);put_u32(b.data()+180,s.cylinder_retard_floor_mask);
 const unsigned idle_index[]={0,2,3,4,5,1};for(unsigned i=0;i<6;++i)value(216+i*4,s.idle_proposals[idle_index[i]]);
 put_u32(b.data()+240,s.idle_flags|(s.idle_available&&s.has(engine::Present)?256U:0U));put_u32(b.data()+244,s.idle_state);put_u32(b.data()+248,s.idle_reason);put_u32(b.data()+252,s.idle_algorithm);
 put_u32(b.data()+208,s.input_valid);
 const auto sample_age=engine::data_age_us(s,s.sampled_us,now);
 const bool fresh=age<=1000000&&sample_age<=1000000;
 put_u32(b.data()+212,(s.flags&~engine::DisplayFresh)|(fresh?engine::DisplayFresh:0));
 const auto&ae=s.transient_enrichment;
 for(unsigned i=0;i<transient::value_count;++i)value(256+i*4,ae.available?ae.values[i]:0);
 put_u32(b.data()+288,ae.flags|(ae.available?256U:0U));put_u32(b.data()+292,static_cast<unsigned>(ae.mode));
 put_u32(b.data()+296,static_cast<unsigned>(ae.apply));put_u32(b.data()+300,static_cast<unsigned>(ae.phase));put_u32(b.data()+304,static_cast<unsigned>(ae.reason));
 const auto&m=s.load_model;
 for(unsigned i=0;i<load::value_count;++i){
  if(m.available&&engine::finite(m.values[i]))put_float(b.data()+320+i*4,m.values[i]);
  else put_u32(b.data()+320+i*4,0x7fc00000);
 }
 const auto model_flags=std::uint32_t(m.flags)|(m.available?65536U:0U)|(m.available&&engine::finite(m.values[load::AfrFactor])?131072U:0U)|(std::uint32_t(m.reason)<<24);
 put_u32(b.data()+356,model_flags);put_u32(b.data()+360,static_cast<unsigned>(m.fuel));put_u32(b.data()+364,static_cast<unsigned>(m.spark));
 put_u32(b.data()+368,static_cast<unsigned>(m.lambda));put_u32(b.data()+372,static_cast<unsigned>(m.trim));put_u32(b.data()+376,static_cast<unsigned>(m.pressure));
 put_u32(b.data()+380,static_cast<unsigned>(m.aux_role));put_u32(b.data()+384,static_cast<unsigned>(m.baro_source));put_u32(b.data()+388,static_cast<unsigned>(m.afr));
 const secondary::Observation*second[]={&s.secondary_fuel,&s.secondary_spark};
 for(unsigned n=0;n<2;++n){const auto&o=*second[n];const unsigned offset=416+n*80;
  for(unsigned v=0;v<9;++v){const float number=o.*secondary::value_members[v];if(o.available&&engine::finite(number))put_float(b.data()+offset+v*4,number);else put_u32(b.data()+offset+v*4,0x7fc00000);}
  put_u32(b.data()+offset+36,secondary::flags(o));
  const unsigned codes[]={static_cast<unsigned>(o.mode),static_cast<unsigned>(o.cells),static_cast<unsigned>(o.source),static_cast<unsigned>(o.reason),static_cast<unsigned>(o.input_source),static_cast<unsigned>(o.condition)};
  for(unsigned code=0;code<6;++code)put_u32(b.data()+offset+40+code*4,codes[code]);
  put_u32(b.data()+offset+64,static_cast<std::uint32_t>(o.input_observed_us));put_u32(b.data()+offset+68,static_cast<std::uint32_t>(o.input_observed_us>>32));
 }
}
} // namespace ecu::tuning
