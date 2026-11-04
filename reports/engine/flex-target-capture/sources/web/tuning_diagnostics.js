/* Read-only tuning transport observations. USB bus presence is not an app link. */
'use strict';
window.EcuTuningDiagnostics=(()=>{
 let generation=0,timer;
 const esc=value=>String(value??'unknown').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function rows(entries){return entries.map(([label,value])=>`<div class="keyline"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join('');}
 function render(data){
  const s=data.session,w=data.wire;
  const entries=[['Transport',data.transport],['Controller identity',data.identity],['Serial protocol',data.serial_protocol],['Service available',data.available?'yes':'no'],['Status',data.reason],['USB bus present',data.host_present===null?'not measured':data.host_present?'yes':'no'],['RX driver drops',data.driver_rx_drop_count??'unknown']];
  if(s)entries.push(['Write state',s.state],['Staged edits',s.dirty?'yes':'no'],['Session origin revision',s.origin_revision],['Expected backend revision',s.base_revision],['Observed active revision',s.observed_active_revision||'unavailable'],['Last command code','0x'+Number(s.last_code).toString(16).padStart(2,'0')],['Successful whole-tune burns',s.burns],['Rejected commands',s.rejected]);
  if(w)entries.push(['CRC errors',w.crc_errors],['Partial-frame timeouts',w.timeouts],['Framing errors',w.framing_errors],['Reply queue failures',w.tx_errors]);
  if(data.session_count!==undefined)entries.push(['Host development sessions',data.session_count]);
  return rows(entries)+`<p class="hint">${esc(data.host_presence_meaning)}</p><p class="hint">${esc(data.commit_behavior)}</p><p class="warn">${esc(data.application_support)}</p><p class="hint">${esc(data.qualification)}</p>`;
 }
 function attach(root,{api,file,toast}){
  const mine=++generation;clearTimeout(timer);let latest;
  root.innerHTML='<section class="panel" style="margin-top:20px"><div class="panelhead"><h2>Tuning connection</h2><button id="engine-tuning-export" class="small ghost">Export diagnostics</button></div><div id="engine-tuning-status" class="panelbody"><p class="hint">Loading tuning diagnostics.</p></div></section>';
  root.querySelector('button').onclick=()=>{if(latest)file('ecu-tuning-diagnostics.json',JSON.stringify(latest,null,2)+'\n','application/json');else toast('No tuning observation yet.',true);};
  async function poll(){
   if(mine!==generation||!root.isConnected)return;
   try{const data=await api('/api/engine/tuning');if(mine!==generation||!root.isConnected)return;latest=data;root.querySelector('#engine-tuning-status').innerHTML=render(data);}
   catch(error){if(mine===generation&&root.isConnected)root.querySelector('#engine-tuning-status').textContent='Tuning diagnostics unavailable: '+error.message;}
   finally{if(mine===generation&&root.isConnected)timer=setTimeout(poll,1000);}
  }
  poll();
 }
 return {attach};
})();
