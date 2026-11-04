/* A bounded browser collector. Identity/cursor validation precedes every commit. */
'use strict';
window.EcuEngineLogger=(()=>{
 const MAX_ROWS=45000,INPUTS=['rpm','map_kpa','tps_pct','clt_c','iat_c','lambda','battery_v','sensor_v'];
 const PROPOSALS=['rpm','ve_pct','target_lambda','advance_deg','pulse_ms','dwell_ms','deadtime_ms','air_mg','warmup','afterstart','accel','ego','duty_pct','idle_pct'];
 const INPUT_LABELS=['RPM','MAP','TPS','CLT','IAT','Lambda','Battery','Sensor5V'];
 const PROPOSAL_LABELS=['ProposedRPM','VE','LambdaTarget','ProposedAdvance','ProposedPW','ProposedDwell','DeadTime','AirMass','Warmup','Afterstart','Accel','EGO','Duty','IdleProposal'];
 const IDLE_LABELS=['IdleTarget','IdleDuty','IdleFeedforward','IdleP','IdleI','IdleD','IdleFlags','IdleState','IdleReason','IdleAlgorithm','IdlePidUpdates','IdleAvailable'],IDLE_VALUES=['target_rpm','duty_pct','feedforward_pct','p_term','i_term','d_term'];
 const AE_VALUES=['tps_dot_pct_s','map_dot_kpa_s','window_ms','trigger_dot','correction_pct','unclamped_pct','remaining_ms','added_fuel_mg'];
 const AE_LABELS=['AeTpsDot','AeMapDot','AeWindowMs','AeTriggerDot','AeCorrectionPct','AeUnclampedPct','AeRemainingAtSampleMs','AeAddedFuelMg','AeFlags','AeMode','AeApply','AePhase','AeReason','AeAvailable'];
 const AE_UNITS=['%/s','kPa/s','ms','source_units/s','%','%','ms','mg','bitfield','code','code','code','code','bool'];
 const LOAD_VALUES=['fuel_load','spark_load','lambda_load','trim_load','pressure_factor','baro_kpa','emap_kpa','aux_kpa','afr_factor'];
 const LOAD_CODES=['flags','fuel_source_code','spark_source_code','lambda_source_code','trim_source_code','pressure_code','aux_role_code','baro_source_code','afr_code','reason_code','afr_state_code'];
 const LOAD_LABELS=['LoadFuel','LoadSpark','LoadLambda','LoadTrim','LoadPressureFactor','LoadBaro','LoadEmap','LoadAux','LoadAfrFactor','LoadFlags','LoadFuelSource','LoadSparkSource','LoadLambdaSource','LoadTrimSource','LoadPressure','LoadAuxRole','LoadBaroSource','LoadAfr','LoadReason','LoadAfrState','LoadAvailable'];
 const LOAD_UNITS=['source_units','source_units','source_units','source_units','ratio','kPa','kPa','kPa','ratio','bitfield',...Array(10).fill('code'),'bool'];
 const PREFIX=['Time','RowSequence','SnapshotSequence','ControlAge','SensorAge','Source','TuneRevision','SensorRevision','PhaseEpoch','Flags','Faults','State','Strategy','PhaseReason','PhaseLosses','CamRejected','CamError','WorkerCommand','WorkerAge','WorkerEpoch','WorkerTuneRevision','WorkerSensorRevision','TimingFault','LastTimingFault','VirtualMask','PhysicalCommandMask','BoardFlags','InputValidMask'];
 const UNITS=['s','count','count','ms','ms','code','count','count','count','bitfield','bitfield','code','code','code','count','count','deg','count','ms','count','count','count','code','code','bitfield','bitfield','bitfield','bitfield',
  'RPM','kPa','%','C','C','lambda','V','V','RPM','%','lambda','deg','ms','ms','ms','mg','ratio','ratio','ratio','ratio','%','%',...Array(8).fill('count')];
 let root,options,meta,identity,rows=[],gaps=[],cursor=0,error='',collecting=false,timer,polling=false,sampleTimer,generation=0,mount=0;
 const text=(node,value)=>{if(node)node.textContent=String(value??'--');};
 const el=id=>root?.isConnected?root.querySelector('#engine-data-'+id):null;
 const uint=n=>Number.isSafeInteger(n)&&n>=0&&n<=4294967295;
 const u64=s=>typeof s==='string'&&/^(0|[1-9][0-9]{0,19})$/.test(s)&&BigInt(s)<=18446744073709551615n;
 function checkHeader(h){
  if(!h||h.schema_version!==1||!/^[0-9a-f]{32}$/.test(h.boot_id)||!uint(h.log_id)||!uint(h.total)||!uint(h.first_sequence)||!uint(h.next_after??0)||h.capacity!==256||!['idle','recording','timeout','stopped','clock_reversed','counter_limit'].includes(h.state)||!u64(h.started_us)||!u64(h.ended_us)||(h.log_id&&!([1,2].includes(h.source_code))))throw Error('Invalid engine log metadata.');
 }
 function adopt(h){checkHeader(h);++generation;meta=h;identity={boot_id:h.boot_id,log_id:h.log_id};rows=[];gaps=[];cursor=0;error='';}
 function acceptPage(p){
  checkHeader(p);
  if(!identity||p.boot_id!==identity.boot_id||p.log_id!==identity.log_id||p.snapshot_superseded||p.future_cursor||p.invalid_row||['started_us','period_ms','duration_s','source_code'].some(k=>p[k]!==meta[k]))throw Error('Log identity changed. Collected rows are preserved.');
  if(!Array.isArray(p.records)||p.records.length>16||!uint(p.gap_first)||!uint(p.gap_last))throw Error('Invalid log page.');
  let expected=cursor+1;const staged=[];
  if(p.gap_first||p.gap_last){
   if(p.gap_first!==expected||p.gap_last<p.gap_first||p.gap_last>=p.first_sequence||!p.records.length)throw Error('Invalid lost-row range.');
   expected=p.gap_last+1;
  }
  for(const r of p.records){
   const s=r?.sample;
   if(r.log_id!==identity.log_id||!uint(r.row_sequence)||r.row_sequence!==expected++||!u64(r.recorded_us)||!s||s.schema_version!==1||!s.available||!u64(s.sequence)||!u64(s.control_us)||!u64(s.sampled_us)||s.source_code!==p.source_code||!s.inputs||!s.proposals||!Array.isArray(s.raw_adc)||s.raw_adc.length!==8||!s.worker_observation||!u64(s.worker_observation.command_sequence))throw Error('Invalid or mixed engine row. Cursor unchanged.');
   const previous=staged.at(-1)||rows.at(-1);
   if(s.cylinders&&(!uint(s.cylinders.valid_mask)||s.cylinders.valid_mask>15||!Array.isArray(s.cylinders.proposals)||s.cylinders.proposals.length!==4))throw Error('Invalid cylinder observation.');
   if(s.idle&&(typeof s.idle.available!=='boolean'||!u64(s.idle.pid_updates)||!uint(s.idle.flags)||!uint(s.idle.state_code)||s.idle.state_code>10||!uint(s.idle.reason_code)||s.idle.reason_code>12||!uint(s.idle.algorithm_code)||s.idle.algorithm_code>2||IDLE_VALUES.some(k=>s.idle.available?!Number.isFinite(s.idle[k]):s.idle[k]!==null)))throw Error('Invalid idle observation.');
   if(s.load_model!==undefined)window.EcuLoadModel.checkObservation(s.load_model,s.available);
   const ae=s.transient_enrichment;
   if(ae!==undefined){
    if(!ae||typeof ae!=='object'||Array.isArray(ae))throw Error('Invalid transient observation.');
    if(typeof ae.available!=='boolean'||!uint(ae.flags)||ae.flags>31||!uint(ae.mode_code)||ae.mode_code>3||!uint(ae.apply_code)||ae.apply_code>1||!uint(ae.phase_code)||ae.phase_code>2||!uint(ae.reason_code)||ae.reason_code>11||AE_VALUES.some(k=>ae.available?ae[k]!==null&&!Number.isFinite(ae[k]):ae[k]!==null))throw Error('Invalid transient observation.');
    if(ae.available&&(Boolean(ae.flags&2)!==Boolean(ae.phase_code)||!Number.isFinite(ae.correction_pct)||ae.correction_pct<0||!Number.isFinite(ae.remaining_ms)||ae.remaining_ms<0||ae.remaining_ms>2000||!Number.isFinite(ae.added_fuel_mg)||ae.added_fuel_mg<0||((ae.flags&1)&&(!Number.isFinite(ae[ae.mode_code===3?'map_dot_kpa_s':'tps_dot_pct_s'])||!Number.isFinite(ae.window_ms)||ae.window_ms<=0))))throw Error('Invalid transient rate/phase.');
   }
   if(BigInt(s.sequence)===0n||BigInt(r.recorded_us)<BigInt(p.started_us)||BigInt(s.control_us)>BigInt(r.recorded_us)||BigInt(s.sampled_us)>BigInt(r.recorded_us)||
    (previous&&(BigInt(s.sequence)<=BigInt(previous.sample.sequence)||BigInt(r.recorded_us)<BigInt(previous.recorded_us))))throw Error('Invalid source sequence or observation clock. Cursor unchanged.');
   staged.push(r);
  }
  const next=staged.length?staged.at(-1).row_sequence:cursor;
  if(p.next_after!==next||next>p.total||rows.length+staged.length>MAX_ROWS)throw Error('Invalid cursor or browser row limit reached. Export collected rows.');
  if(p.gap_first)gaps.push([p.gap_first,p.gap_last]);
  rows.push(...staged);cursor=next;meta=p;return staged.length;
 }
 function headers(){return {'X-ECU-Log-Boot':identity.boot_id};}
 function paint(){
  const h=meta;const missing=gaps.reduce((sum,[a,b])=>sum+b-a+1,0);
  text(el('summary'),h?`${h.state} / ${h.data_source} / ${rows.length} browser rows / ${h.retained} retained on device / ${h.total} recorded`:'Loading recorder metadata...');
  text(el('gaps'),h?`${missing} rows missed by this browser; ${h.overwritten} overwritten on device; ${h.missed_periods} sampling periods missed; ${h.repeated_skipped} repeated snapshots skipped; ${h.invalid_skipped} invalid observations skipped. Producer lock contentions: ${h.producer_lock_contention_attempts??0}.`:'');
  text(el('error'),error);text(el('identity'),identity?`Boot ${identity.boot_id} / log ${identity.log_id} / collected through row ${cursor}`:'No log selected');
  if(el('stop'))el('stop').disabled=!h||h.state!=='recording';
  if(el('start'))el('start').disabled=!h||h.state==='recording'||h.export_busy||polling;
  if(el('msl'))el('msl').disabled=!rows.length;
  if(el('json'))el('json').disabled=!rows.length;
  if(el('retained'))el('retained').disabled=!h||h.state==='recording'||!h.retained;
 }
 async function collect(){
  if(polling||!collecting||!identity?.log_id)return;
  polling=true;clearTimeout(timer);const selected=generation;
  try{
   for(let i=0;i<8;++i){
    const page=await options.api(`/api/engine/data-log?log_id=${identity.log_id}&after=${cursor}`,{headers:headers()});
    if(selected!==generation)return;
    const count=acceptPage(page);error='';
    if(cursor>=page.total){if(page.state!=='recording')collecting=false;break;}
    if(!count)throw Error('Log page made no progress. Collected rows are preserved.');
   }
  }catch(e){if(selected===generation){error=e.message;if(/identity|changed|boot|limit|Invalid/.test(error))collecting=false;}}
  finally{polling=false;paint();if(collecting)timer=setTimeout(collect,error?1000:250);}
 }
 async function metadata(follow=false){
  const h=await options.api('/api/engine/data-log');checkHeader(h);
  if(!identity||follow){adopt(h);collecting=!!h.log_id;}
  else if(h.boot_id!==identity.boot_id||h.log_id!==identity.log_id){error='Device log changed. Export the collected rows before choosing Follow current log.';collecting=false;}
  else meta=h;
  paint();if(collecting)collect();
 }
 function file(name,contents,type){options.file(name,contents,type);}
 const number=value=>typeof value==='number'&&Number.isFinite(value)?String(Number(value.toPrecision(9))):'NaN';
 function exportMsl(){
  if(!meta||!rows.length)throw Error('No collected engine rows.');
  const lines=['"ESP32ECU ENGINE LOG 005"',`"BROWSER COLLECTED ${meta.source_code===1?'TARGET OBSERVATIONS':'SYNTHETIC REPLAY'} / boot ${identity.boot_id} / log ${identity.log_id} / period_ms=${meta.period_ms} duration_s=${meta.duration_s} / overwritten=${meta.overwritten} missed_periods=${meta.missed_periods} repeated=${meta.repeated_skipped} invalid=${meta.invalid_skipped} / missing row ranges ${gaps.map(x=>x.join('..')).join(',')||'none'} / PhaseEpoch=configuration context; WorkerEpoch=executor generation / proposals and software command masks; no electrical execution measurement"`,
   [...PREFIX,...INPUT_LABELS,...PROPOSAL_LABELS,...Array.from({length:8},(_,i)=>'ADC'+i),'CylinderValidMask','CylinderTrimsEnabled','CylinderCapacityMask','CylinderSparkClampMask','CylinderRetardFloorMask',...Array.from({length:4},(_,i)=>['PW','Advance','FuelTrim','Duty'].map(k=>'C'+(i+1)+k)).flat(),...IDLE_LABELS,...AE_LABELS,...LOAD_LABELS].join('\t'),[...UNITS,'bitfield','bool','bitfield','bitfield','bitfield',...Array(4).fill(['ms','deg','%','%']).flat(),'RPM','%','%','%','%','%','bitfield','code','code','code','count','bool',...AE_UNITS,...LOAD_UNITS].join('\t')];
  for(const r of rows){
   const s=r.sample,w=s.worker_observation,c=s.cylinders,ae=s.transient_enrichment,model=s.load_model;const extra=[c?.valid_mask||0,c?.enabled?1:0,c?.capacity_mask||0,c?.spark_clamp_mask||0,c?.retard_floor_mask||0,...Array.from({length:4},(_,i)=>['pulse_ms','advance_deg','fuel_pct','duty_pct'].map(k=>number(c?.valid_mask&(1<<i)?c.proposals[i][k]:null))).flat()];const elapsed=Number(BigInt(r.recorded_us)-BigInt(meta.started_us))/1e6;
   lines.push([elapsed.toFixed(6),r.row_sequence,s.sequence,number(s.control_age_ms),number(s.sample_age_ms),s.source_code,s.tune_revision,s.sensor_revision,s.phase_epoch,s.flags,s.controller_faults,s.state_code,s.strategy_code,s.phase_reason_code,s.phase_losses,s.cam_rejected,number(s.cam_error_deg),w.command_sequence,number(w.age_ms),w.epoch,w.tune_revision,w.sensor_revision,w.timing_fault_code,w.last_timing_fault_code,w.virtual_high_mask,w.physical_command_mask,s.board_flags,s.input_valid_mask,
    ...INPUTS.map(k=>number(s.inputs[k])),...PROPOSALS.map(k=>number(s.proposals[k])),...s.raw_adc.map(number),...extra,...IDLE_VALUES.map(k=>number(s.idle?.available?s.idle[k]:null)),s.idle?.flags??0,s.idle?.state_code??0,s.idle?.reason_code??0,s.idle?.algorithm_code??0,s.idle?.pid_updates??'0',s.idle?.available?1:0,...AE_VALUES.map(k=>number(ae?.available?ae[k]:null)),ae?.flags??0,ae?.mode_code??0,ae?.apply_code??0,ae?.phase_code??0,ae?.reason_code??3,ae?.available?1:0,...LOAD_VALUES.map(k=>number(model?.available&&Number.isFinite(model[k])?Math.fround(model[k]):null)),...LOAD_CODES.map((k,i)=>model?.[k]??([5,8].includes(i)?1:i===10?255:0)),model?.available?1:0].join('\t'));
  }
  return lines.join('\n')+'\n';
 }
 async function command(action){
  if(polling)return;
  try{
   if(action==='start'){
    const h=await options.api('/api/engine/data-log');checkHeader(h);
    const next=await options.api('/api/engine/data-log',{method:'POST',headers:{'X-ECU-Log-Boot':h.boot_id},body:JSON.stringify({action:'start',period_ms:Number(el('period').value),duration_s:Number(el('duration').value)})});
    adopt(next);collecting=true;
   }else{
    const h=await options.api('/api/engine/data-log',{method:'POST',headers:headers(),body:JSON.stringify({action:'stop',log_id:identity.log_id})});
    checkHeader(h);if(h.boot_id!==identity.boot_id||h.log_id!==identity.log_id)throw Error('Device log changed. Collected rows are preserved.');meta=h;collecting=true;
   }
   error='';paint();await collect();
  }catch(e){error=e.message;paint();options.toast(e.message,true);}
 }
 async function sample(selected=mount){
  if(!root?.isConnected||selected!==mount)return;
  try{
   const s=await options.api('/api/engine/sample');if(!root?.isConnected||selected!==mount)return;
   text(el('sample'),s.available?`${s.data_source}${s.historical?' / completed historical replay':''} / snapshot ${s.sequence} / control age ${s.control_age_ms??'unknown'} ms / sensor age ${s.sample_age_ms??'unknown'} ms / ${s.display_fresh?'fresh display observation':'stale or historical observation'}`:'No completed control sample yet.');
   const w=s.worker_observation;
   text(el('values'),s.available?`Input RPM ${s.inputs.rpm??'invalid'} / MAP ${s.inputs.map_kpa??'invalid'} kPa / TPS ${s.inputs.tps_pct??'invalid'} % / lambda ${s.inputs.lambda??'invalid'}. Proposed fuel ${number(s.proposals.pulse_ms)} ms / spark ${number(s.proposals.advance_deg)} °BTDC / dwell ${number(s.proposals.dwell_ms)} ms. Tune ${s.tune_revision}, sensors ${s.sensor_revision}. Worker observed command ${w.command_sequence}, age ${w.age_ms??'unknown'} ms, command mask ${w.physical_command_mask}.`:'Inputs and proposals are unavailable.');
  }catch(e){if(selected===mount){text(el('sample'),'Control sample unavailable: '+e.message);text(el('values'),'Previously displayed values are unavailable.');}}
  finally{if(root?.isConnected&&selected===mount)sampleTimer=setTimeout(()=>sample(selected),500);}
 }
 async function attach(node,config){
  clearTimeout(sampleTimer);++mount;root=node;options=config;
  root.innerHTML=`<section class="panel" style="margin-top:20px"><div class="panelhead"><h2>Control sample & engine log</h2><span class="tag">OBSERVATIONS / OUTPUTS INHIBITED</span></div><div class="panelbody"><p class="fine" id="engine-data-sample">Loading coherent control sample...</p><p class="fine" id="engine-data-values"></p><p class="hint">Inputs and proposals belong to one completed control step. The worker command was observed earlier. Submission and software masks do not establish electrical execution.</p><div class="divider"></div><div class="formgrid"><div class="field"><label for="engine-data-period">Log period</label><select id="engine-data-period">${[20,50,100,200,500,1000].map(ms=>`<option value="${ms}" ${ms===100?'selected':''}>${ms} ms</option>`).join('')}</select></div><div class="field"><label for="engine-data-duration">Log duration (seconds)</label><input id="engine-data-duration" type="number" min="1" max="900" step="1" value="12"></div></div><div class="actions" style="margin-top:12px"><button id="engine-data-start">${config.simulator?'Replay completed SIL log':'Start target log'}</button><button id="engine-data-stop" disabled>Stop log</button><button id="engine-data-follow">Follow current log</button><button id="engine-data-msl" disabled>Export collected MSL</button><button id="engine-data-json" disabled>Export collected JSON</button><button id="engine-data-retained" disabled>Export retained window</button></div><p class="hint">${config.simulator?'The host replays the end of a completed SIL run through the same native recorder, without waiting in real time.':'The device records to RAM. This tab collects rows while it stays open.'} The device retains 256 rows (25.6 s at 100 ms, 5.12 s at 20 ms). Browser collection is limited to 45,000 rows. Pausing, closing or throttling this tab can lose older rows. A new log replaces this browser collection. Export before starting or following another log. Logs are lost on device reboot.</p><p class="fine" id="engine-data-summary" role="status"></p><p class="fine" id="engine-data-gaps"></p><p class="fine mono" style="overflow-wrap:anywhere" id="engine-data-identity"></p><p class="warn" role="alert" id="engine-data-error"></p></div></section>`;
  el('start').onclick=()=>command('start');el('stop').onclick=()=>command('stop');
  el('follow').onclick=()=>metadata(true).catch(e=>{error=e.message;paint();});
  el('msl').onclick=()=>file('ecu-collected-engine.msl',exportMsl(),'text/plain');
  el('json').onclick=()=>file('ecu-collected-engine.json',JSON.stringify({schema_version:1,identity,metadata:meta,gaps,scope:'Browser collected observations only; missing row ranges are not filled',records:rows},null,2),'application/json');
  el('retained').onclick=async()=>{try{
   const r=await fetch(`/api/engine/data-log.msl?log_id=${identity.log_id}&after=0`,{headers:{...headers(),'X-ECU-Token':options.token},signal:AbortSignal.timeout(15000)});
   if(!r.ok){const j=await r.json();throw Error(j.error||'Retained export failed.');}
   file('ecu-retained-engine.msl',await r.text(),'text/plain');
  }catch(e){error=e.message;paint();}};
  sample();try{await metadata();}catch(e){error=e.message;paint();}
 }
 function detach(){clearTimeout(sampleTimer);++mount;root=null;}
 return {attach,detach,acceptPage,exportMsl,adopt,inspect:()=>({identity,cursor,rows:rows.length,gaps:[...gaps],collecting,error}),MAX_ROWS};
})();
