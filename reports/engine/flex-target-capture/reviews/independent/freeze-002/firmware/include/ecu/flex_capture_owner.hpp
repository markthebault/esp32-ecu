#pragma once
#include "ecu/flex_engine.hpp"
#include "ecu/flex_ingress.hpp"

namespace ecu::flex {
struct CaptureRequest {
 CaptureConfig calibration;
 std::uint32_t tune_revision=0,sensor_revision=0;
 bool required=false,confirmed=false;
};
inline bool same(const CaptureRequest&a,const CaptureRequest&b){return
 same(a.calibration,b.calibration)&&a.tune_revision==b.tune_revision&&a.sensor_revision==b.sensor_revision&&
 a.required==b.required&&a.confirmed==b.confirmed;
}
struct CaptureVersion {
 std::uint64_t context=0,generation=0,armed_after_us=0;
 bool armed=false;
};
ECU_ISR_CODE bool same(CaptureVersion a,CaptureVersion b){return a.context==b.context&&a.generation==b.generation&&a.armed_after_us==b.armed_after_us&&a.armed==b.armed;}
struct CaptureTicket {
 CaptureVersion version;
 std::uint64_t publication=0,sample_us=0,valid_until_us=0;
 bool required=false,qualified=false;
};
struct CaptureWork {
 CaptureRequest request;CaptureVersion version;IngressSnapshot ingress;
 std::uint32_t external_epoch=0;
 bool binding=false,available=false,active=false;
};
struct CaptureView {
 Sample sample;
 CaptureTicket ticket;
 IngressTicket ingress_ticket;
 std::uint64_t published_us=0;
 bool present=false,current=false,ack_eligible=false;
};
struct CapturePortSnapshot {
 CaptureWork work;CaptureView view;
 std::uint64_t rejected_publications=0,rejected_acks=0,acks=0;
};

// All methods require one external serialization, with time sampled AFTER
// taking that lock. The ISR uses only push/version/can_dispatch. No floating
// point processing, SDK access, allocation or fault ACK occurs in those paths.
class CapturePort {
 Ingress ingress_;
 CaptureRequest request_;
 CaptureView published_;
 std::uint64_t context_=0,publication_=0,stale_us_=0;
 std::uint64_t rejected_publications_=0,rejected_acks_=0,acks_=0;
 std::uint32_t epoch_=0;
 bool configured_=false,binding_=false,available_=false,active_=false,fenced_=false,terminal_=false;
 static void increment(std::uint64_t&v){if(v!=UINT64_MAX)++v;}
 ECU_ISR_CODE bool matches(CaptureVersion expected)const{return same(expected,version());}
public:
 ECU_ISR_CODE CaptureVersion version()const{
  const auto f=ingress_.fence();return {f.context,f.generation,f.armed_after_us,f.armed};
 }
 ECU_ISR_CODE bool required()const{return request_.required;}
 ECU_ISR_CODE bool armed()const{return ingress_.fence().armed;}
 // Called synchronously at every external configuration/inhibition fence.
 // The target masks/clears only the flex channel before this call.
 void fence(std::uint64_t now){ingress_.stop(now);fenced_=true;active_=false;}
 bool changes(const CaptureRequest&r,std::uint32_t epoch,bool binding,bool available,bool calibration_valid,std::uint64_t stale_us)const{
  const bool effective=binding&&calibration_valid&&stale_us>=250000&&stale_us<=2000000&&!terminal_;
  return !configured_||fenced_||epoch!=epoch_||effective!=binding_||available!=available_||!same(r,request_);
 }
 CaptureWork configure(const CaptureRequest&r,std::uint32_t epoch,bool binding,bool available,bool calibration_valid,
                       std::uint64_t stale_us,std::uint64_t now){
  const bool changed=changes(r,epoch,binding,available,calibration_valid,stale_us);
  if(changed){
   if(context_==UINT64_MAX){terminal_=true;ingress_.begin_context(0,now);}
   else{++context_;ingress_.begin_context(context_,now);}
   ingress_.stop(now);request_=r;epoch_=epoch;configured_=true;
  }else ingress_.begin_context(context_,now); // Also validates owner clock order.
  binding_=binding&&calibration_valid&&stale_us>=250000&&stale_us<=2000000&&!terminal_;available_=available;fenced_=false;
  stale_us_=stale_us;active_=binding_&&available_&&r.required&&r.confirmed;
  if(!active_)ingress_.stop(now);
  return work();
 }
 CaptureWork work()const{
  CaptureWork w;w.request=request_;w.version=version();w.ingress=ingress_.snapshot();w.external_epoch=epoch_;
  w.binding=binding_&&!fenced_;w.available=available_;w.active=active_&&!fenced_;return w;
 }
 bool arm(CaptureVersion expected,std::uint64_t now){
  if(!active_||fenced_||!matches(expected))return false;
  return ingress_.arm(context_,now);
 }
 ECU_ISR_CODE Ingress::Result push(std::uint64_t captured,std::uint64_t observed,bool high,bool clock_ok,std::uint32_t raw){
  const auto result=ingress_.push(context_,captured,observed,high,clock_ok,raw);
  return active_&&!fenced_?result:Ingress::Result::Suppress;
 }
 bool pop(CaptureVersion expected,IngressEdge&edge){
  if(!active_||fenced_||!matches(expected)||!expected.armed)return false;
  return ingress_.pop(edge);
 }
 bool publish(CaptureVersion expected,const Sample&sample,std::uint64_t now){
  if(publication_==UINT64_MAX){terminal_=true;binding_=active_=false;ingress_.stop(now);increment(rejected_publications_);return false;}
  const auto&o=sample.observation;
  const bool identity=sample.tune_revision==request_.tune_revision&&same(sample.calibration,request_.calibration);
  const bool origin=o.source==Source::Unavailable||o.source==Source::TargetCapture;
  const auto f=ingress_.fence();
  const bool valid_sample=!o.valid||(active_&&f.armed&&!f.pending&&o.source==Source::TargetCapture&&
   !o.pending_fault&&o.fault_generation==o.acknowledged_generation&&o.sample_us<=o.last_edge_us&&o.last_edge_us<=now&&
   stale_us_&&o.sample_us<=UINT64_MAX-stale_us_-1&&now-o.sample_us<=stale_us_);
  if(!matches(expected)||!identity||!origin||!valid_sample||(published_.present&&now<published_.published_us)){increment(rejected_publications_);return false;}
  published_={};published_.present=true;published_.sample=sample;published_.published_us=now;
  auto&t=published_.ticket;t.version=expected;t.publication=++publication_;t.required=request_.required;
  t.qualified=o.valid&&binding_&&!fenced_;t.sample_us=o.sample_us;
  if(t.qualified)t.valid_until_us=o.sample_us+stale_us_;
  if(request_.required&&o.pending_fault&&!o.valid&&binding_&&!fenced_){
   published_.ack_eligible=true;if(f.pending)published_.ingress_ticket=ingress_.offer_fault();
  }
  return true;
 }
 CaptureView view(std::uint64_t now)const{
  auto v=published_;
  v.current=v.present&&binding_&&!fenced_&&matches(v.ticket.version)&&now>=v.published_us;
  if(v.sample.observation.valid)v.current=v.current&&now>=v.ticket.sample_us&&now<=v.ticket.valid_until_us;
  v.ack_eligible=v.ack_eligible&&v.current;return v;
 }
 // A completed invalid control result reaches the owner before this call.
 // Exact publication identity prevents diagnostics, an old control result or
 // a newly faulted/configured producer from clearing the current notification.
 bool acknowledge(const CaptureView&consumed,std::uint64_t now){
  const auto current=view(now);
  if(!current.current||!current.ack_eligible||!consumed.ack_eligible||
     consumed.ticket.publication!=current.ticket.publication||!same(consumed.ticket.version,current.ticket.version)||
     consumed.sample.observation.fault_generation!=current.sample.observation.fault_generation){increment(rejected_acks_);return false;}
  if(current.ingress_ticket&&!ingress_.acknowledge(current.ingress_ticket,now)){increment(rejected_acks_);return false;}
  published_.ack_eligible=false;increment(acks_);return true;
 }
 // Issue binds to the exact genuine publication. The immutable internal
 // command may later use it until its OWN sample deadline, even if a newer
 // publication exists. A newer frame never refreshes an older command.
 bool can_issue(const CaptureTicket&t,std::uint64_t now,bool both_cut)const{
  if(both_cut)return true;
  if(!request_.required)return !t.required;
  const auto v=view(now);
  return v.current&&t.publication==v.ticket.publication&&t.sample_us==v.ticket.sample_us&&
   t.valid_until_us==v.ticket.valid_until_us&&can_dispatch(t,now,false);
 }
 ECU_ISR_CODE bool can_dispatch(const CaptureTicket&t,std::uint64_t now,bool both_cut)const{
  if(both_cut)return true;
  if(!request_.required)return !t.required;
  const auto f=ingress_.fence();
  return active_&&!fenced_&&binding_&&t.required&&t.qualified&&matches(t.version)&&f.armed&&!f.pending&&!f.terminal&&
   now>=t.sample_us&&now<=t.valid_until_us;
 }
 CapturePortSnapshot snapshot(std::uint64_t now)const{
  return {work(),view(now),rejected_publications_,rejected_acks_,acks_};
 }
};

// The serialized monitor/control task alone owns this floating-point state.
// Backend methods atomically lock/version the target port; processing and
// observe() run outside that short port lock. Reads never run this worker.
class CaptureOwner {
 Capture capture_;
 std::uint64_t context_=0,ingress_fault_=0,arm_boundary_=0;
 CaptureView offered_;
 bool series_active_=false,offered_current_=false;
 static Reason transport_reason(IngressFault fault){
  if(fault==IngressFault::Clock)return Reason::ClockFault;
  if(fault==IngressFault::Overflow||fault==IngressFault::RateLimit||fault==IngressFault::SequenceExhausted)return Reason::Overflow;
  return Reason::Unavailable;
 }
public:
 template<class Backend>CaptureView tick(Backend&backend,const CaptureRequest&request){
  const bool valid_config=valid(request.calibration);
  const auto stale=valid_config?static_cast<std::uint64_t>(std::llround(request.calibration.stale_ms*1000.)):0;
  auto w=backend.configure(request,valid_config,stale);
  const auto producer=w.request;
  if(w.version.context!=context_){
   // First configuration has no prior samples/clocks/faults to preserve.
   // Every later context retains the same object and fault/clock history.
   if(!context_)capture_=Capture(producer.calibration);
   else if(!capture_.configure(producer.calibration))capture_.context_changed();
   context_=w.version.context;ingress_fault_=w.ingress.fault_generation;arm_boundary_=0;series_active_=false;
   if(producer.required&&!producer.confirmed)capture_.capture_error(Reason::Unconfirmed);
  }
  if(w.ingress.pending_fault&&w.ingress.fault_generation!=ingress_fault_){
   capture_.capture_error(transport_reason(w.ingress.last_fault));ingress_fault_=w.ingress.fault_generation;
  }
  if(w.active&&!w.version.armed&&!w.ingress.pending_fault){
   backend.arm(w.version);w=backend.work();
  }
  if(!w.active||!w.version.armed){if(series_active_)capture_.restart();series_active_=false;}
  else if(!series_active_||w.version.armed_after_us!=arm_boundary_){capture_.restart();arm_boundary_=w.version.armed_after_us;series_active_=true;}
  if(w.active&&w.version.armed){
   for(unsigned n=0;n<Ingress::capacity;++n){IngressEdge edge;
    if(!backend.pop(w.version,edge))break;
    capture_.edge(edge.captured_us,edge.high,Source::TargetCapture);
   }
  }
  Sample sample{capture_.observe(backend.clock()),producer.calibration,producer.tune_revision};
  offered_current_=backend.publish(w.version,sample);
  if(!offered_current_){capture_.restart();series_active_=false;}
  offered_=backend.view();return offered_;
 }
 template<class Backend>bool control_observed(Backend&backend,const CaptureView&view,const Evaluation&e,bool completed){
  const auto&o=view.sample.observation;
  if(!offered_current_||!completed||!e.required||e.control_ok||!view.current||!view.ack_eligible||!o.pending_fault||o.valid||
     offered_.ticket.publication!=view.ticket.publication||!same(offered_.ticket.version,view.ticket.version)||
     e.sample.tune_revision!=view.sample.tune_revision||!same(e.sample.calibration,view.sample.calibration)||
     e.sample.observation.fault_generation!=o.fault_generation||e.sample.observation.config_epoch!=o.config_epoch||
     !e.sample.observation.pending_fault||e.sample.observation.valid)return false;
  if(!backend.acknowledge(view))return false;
  return capture_.acknowledge(o.fault_generation);
 }
};
} // namespace ecu::flex
