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
 put_u32(b.data()+240,s.idle_flags);put_u32(b.data()+244,s.idle_state);put_u32(b.data()+248,s.idle_reason);put_u32(b.data()+252,s.idle_algorithm);
 put_u32(b.data()+208,s.input_valid);
 const auto sample_age=engine::data_age_us(s,s.sampled_us,now);
 const bool fresh=age<=1000000&&sample_age<=1000000;
 put_u32(b.data()+212,(s.flags&~engine::DisplayFresh)|(fresh?engine::DisplayFresh:0));
}
} // namespace ecu::tuning
