'use strict';
let triggerFrame=null,triggerTimer,triggerView=0,triggerRead=0,triggerBusy=false;
function leaveTriggers(){clearTimeout(triggerTimer);++triggerView;triggerBusy=false;}
function triggerVisible(view){return current==='triggers'&&view===triggerView;}
function triggerHeader(frame){
 if(frame.schema_version!==1||!Number.isInteger(frame.frame_id)||frame.frame_id<0||frame.frame_id>4294967295||
    !Number.isInteger(frame.count)||frame.count<0||frame.count>512||frame.snapshot_superseded!==false||
    !['idle','armed','full','timeout','stopped','clock_reversed'].includes(frame.state))throw Error('Invalid or replaced trigger frame. Reload the capture.');
 return frame;
}
async function readTriggerFrame(header,keep=()=>true){
 triggerHeader(header);const records=[];
 if(header.state==='armed')return {...header,records};
 for(let offset=0;offset<header.count;offset+=64){
  if(!keep())throw Error('Trigger view changed.');
  const part=triggerHeader(await api(`/api/engine/trigger-log?frame_id=${header.frame_id}&offset=${offset}`));
  const count=Math.min(64,header.count-offset);
  if(part.frame_id!==header.frame_id||part.count!==header.count||part.state!==header.state||part.offset!==offset||part.returned!==count||!Array.isArray(part.records)||part.records.length!==count)throw Error('Trigger capture changed during download. Reload it.');
  for(const [i,row] of part.records.entries()){
   if(row.sequence!==offset+i+1||!['crank','cam'].includes(row.channel)||typeof row.high!=='boolean'||row.timebase_valid!==true||
      !Number.isSafeInteger(row.captured_us)||row.captured_us<0||!Number.isSafeInteger(row.callback_us)||row.callback_us<row.captured_us||
      !Number.isInteger(row.configuration_epoch)||row.configuration_epoch<0||row.configuration_epoch>4294967295||
      !(row.raw_counter===null||Number.isInteger(row.raw_counter)&&row.raw_counter>=0&&row.raw_counter<=4294967295))throw Error('Trigger record is invalid. No export was produced.');
   records.push(row);
  }
 }
 const final=triggerHeader(await api('/api/engine/trigger-log'));
 if(final.frame_id!==header.frame_id||final.count!==header.count||final.state!==header.state)throw Error('A new capture replaced this frame. Reload it.');
 return {...header,records};
}
function renderTriggers(p){
 clearTimeout(triggerTimer);const view=++triggerView;triggerBusy=false;
 p.innerHTML=`<div class="banner"><b>INPUT DIAGNOSTICS</b><span>J17 crank and J18 cam, after Hall conditioning. Physical outputs remain inhibited. Digital captures do not measure sensor voltage or establish cam phase.</span></div><section class="panel"><div class="panelhead"><h2>Crank / cam recording</h2><span id="trigger-state" class="pill unset">LOADING</span></div><div class="panelbody"><div class="formgrid"><div class="field"><label for="trigger-samples">Maximum recorded edges</label><select id="trigger-samples"><option>128</option><option>256</option><option>512</option></select></div><div class="field"><label for="trigger-timeout">Recording window (ms)</label><input id="trigger-timeout" type="number" min="50" max="5000" step="50" value="1000"></div></div><div class="actions" style="margin-top:16px"><button class="primary" id="trigger-start">${session.simulator?'Replay SIL window':'Record trigger window'}</button><button id="trigger-stop" disabled>Stop recording</button><button id="trigger-reload">Reload capture</button><button id="trigger-json" disabled>Export trigger JSON</button><button id="trigger-msl" disabled>Export trigger MSL</button></div><p id="trigger-status" class="fine" role="status" aria-live="polite">Loading recorder...</p><p id="trigger-source" class="hint"></p><p class="hint">The frame freezes at its edge limit, timeout or Stop. Host replay uses the final window of a completed SIL run and contains rising crank edges only. Run a scenario in Engine development first.</p><p class="hint">At J17/J18, verify ground and a compatible 5 V Hall interface before applying an isolated test signal. A raw VR sensor requires a conditioner. Keep actuator harnesses disconnected.</p></div></section><section class="panel" style="margin-top:18px"><div class="panelhead"><h2>Recorded inputs and tooth intervals</h2><span id="trigger-frame-id" class="eyebrow">NO FRAME</span></div><div class="panelbody"><div class="formgrid"><div class="field"><label for="trigger-zoom">Zoom</label><input id="trigger-zoom" type="range" min="1" max="20" value="1"></div><div class="field"><label for="trigger-pan">Window position</label><input id="trigger-pan" type="range" min="0" max="100" value="0"></div></div><p id="trigger-window" class="fine"></p><svg id="trigger-scope" role="img" aria-label="Recorded crank and cam input edges" style="width:100%;height:190px;display:block"></svg><svg id="trigger-periods" role="img" aria-label="Intervals between recorded rising crank edges" style="width:100%;height:180px;display:block"></svg><div id="trigger-summary" class="fine"></div><p class="hint">Long intervals above 1.5 × median are highlighted. Intentional missing teeth, signal loss and lost captures can all make long intervals. A digital trace cannot distinguish these causes by itself.</p><details><summary>Raw recorded edges</summary><div id="trigger-rows" class="tablewrap" style="max-height:320px"></div></details></div></section>`;
 $('#trigger-start').onclick=()=>triggerAction({action:'start',samples:Number($('#trigger-samples').value),timeout_ms:Number($('#trigger-timeout').value)},view);
 $('#trigger-stop').onclick=()=>triggerAction({action:'stop',frame_id:triggerFrame?.frame_id||0},view);
 $('#trigger-reload').onclick=()=>refreshTriggers(view);
 $('#trigger-json').onclick=()=>{if(triggerFrame?.records.length===triggerFrame?.count)download('ecu-trigger-capture.json',triggerFrame)};
 $('#trigger-msl').onclick=()=>{try{engineFile('ecu-trigger-capture.msl',triggerToMsl(triggerFrame),'text/plain')}catch(e){toast(e.message,true)}};
 $('#trigger-zoom').oninput=$('#trigger-pan').oninput=drawTriggerCharts;
 refreshTriggers(view);
}
async function triggerAction(command,view){
 if(triggerBusy||!triggerVisible(view))return;
 triggerBusy=true;++triggerRead;clearTimeout(triggerTimer);$('#trigger-start').disabled=true;$('#trigger-stop').disabled=true;
 try{const frame=await api('/api/engine/trigger-log',{method:'POST',body:JSON.stringify(command)});if(triggerVisible(view))await refreshTriggers(view,frame.frame_id)}
 catch(e){if(triggerVisible(view))toast(e.message,true)}
 finally{if(triggerVisible(view)){triggerBusy=false;$('#trigger-start').disabled=triggerFrame?.state==='armed'||triggerFrame?.available===false;$('#trigger-stop').disabled=triggerFrame?.state!=='armed';}}
}
async function refreshTriggers(view=triggerView,expected=null){
 clearTimeout(triggerTimer);const request=++triggerRead,keep=()=>triggerVisible(view)&&request===triggerRead;
 try{
  const header=triggerHeader(await api('/api/engine/trigger-log'));
  if(expected!==null&&header.frame_id!==expected)throw Error('Another capture replaced the requested frame. Reload it.');
  const frame=await readTriggerFrame(header,keep);if(!keep())return;
  triggerFrame=frame;const armed=frame.state==='armed',ready=!armed&&frame.records.length===frame.count&&frame.count>0;
  $('#trigger-state').textContent=frame.state.toUpperCase();$('#trigger-state').className='pill'+(armed?' unset':frame.state==='clock_reversed'?' fault':'');
  $('#trigger-status').textContent=`Frame ${frame.frame_id}: ${frame.count} / ${frame.requested} edges. ${frame.prearm_ignored||0} pre-arm and ${frame.invalid_timebase_ignored||0} unresolved timestamps ignored.`;
  $('#trigger-source').textContent=(frame.simulator?'COMPLETED SYNTHETIC SIL. ':'MCU DIGITAL CAPTURE. ')+(frame.qualification||'');
  if(frame.available===false)$('#trigger-status').textContent+=' '+(frame.simulator?'Run a SIL scenario before replaying.':'Recorder unavailable: '+frame.driver_error);
  $('#trigger-start').disabled=armed||triggerBusy||frame.available===false;$('#trigger-stop').disabled=!armed||triggerBusy;
  $('#trigger-json').disabled=$('#trigger-msl').disabled=!ready;
  $('#trigger-frame-id').textContent=frame.frame_id?'FRAME '+frame.frame_id:'NO FRAME';
  drawTriggerCharts();renderTriggerRows();
  if(armed)triggerTimer=setTimeout(()=>refreshTriggers(view,frame.frame_id),250);
 }catch(e){if(keep()){$('#trigger-status').textContent='Recorder unavailable: '+e.message;$('#trigger-json').disabled=$('#trigger-msl').disabled=true;toast(e.message,true)}}
}
function triggerSeries(frame){
 const rows=[...(frame?.records||[])].sort((a,b)=>a.captured_us-b.captured_us||a.sequence-b.sequence),periods=[];let previous=null;
 for(const row of rows)if(row.channel==='crank'&&row.high){if(previous!==null)periods.push({time:row.captured_us,period:row.captured_us-previous,sequence:row.sequence});previous=row.captured_us;}
 const sorted=periods.map(p=>p.period).sort((a,b)=>a-b),median=sorted.length?(sorted[Math.floor((sorted.length-1)/2)]+sorted[Math.floor(sorted.length/2)])/2:0;
 return {rows,periods,median};
}
function drawTriggerCharts(){
 const scope=document.querySelector('#trigger-scope'),plot=document.querySelector('#trigger-periods');if(!scope||!plot)return;
 const {rows,periods,median}=triggerSeries(triggerFrame),width=Math.max(280,scope.getBoundingClientRect().width),left=54,right=width-12;
 scope.setAttribute('viewBox',`0 0 ${width} 190`);plot.setAttribute('viewBox',`0 0 ${width} 180`);
 const text=(x,y,value,fill='var(--sub)',anchor='start')=>`<text x="${x}" y="${y}" fill="${fill}" text-anchor="${anchor}" font-size="10" font-family="var(--mono)">${esc(value)}</text>`;
 if(!rows.length){scope.innerHTML=text(left,75,triggerFrame?.state==='armed'?'Recording input edges...':'No recorded input edges');plot.innerHTML='';$('#trigger-window').textContent='';$('#trigger-summary').textContent='';return;}
 const first=rows[0].captured_us,last=rows.at(-1).captured_us,total=Math.max(1,last-first),span=total/Number($('#trigger-zoom').value),start=first+(total-span)*Number($('#trigger-pan').value)/100,end=start+span;
 const x=time=>left+(time-start)/span*(right-left),axis=height=>Array.from({length:5},(_,i)=>{const pos=left+i*(right-left)/4,t=start+i*span/4;return `<line x1="${pos}" y1="12" x2="${pos}" y2="${height-22}" stroke="var(--line)"/>`+text(pos,height-5,((t-first)/1000).toFixed(1),undefined,i===0?'start':i===4?'end':'middle');}).join('')+text(right,11,'ms',undefined,'end');
 let digital=axis(190);
 for(const [channel,y,color] of [['crank',42,'var(--green)'],['cam',112,'var(--amber)']]){
  digital+=text(2,y+10,channel.toUpperCase(),color);const values=rows.filter(r=>r.channel===channel),visible=values.filter(r=>r.captured_us>=start&&r.captured_us<=end);
  if(!values.length){digital+=text(left,y+12,triggerFrame?.includes_cam===false&&channel==='cam'?'Not simulated':'No recorded edges');continue;}
  if(!triggerFrame.includes_falling_edges){for(const row of visible)digital+=`<line x1="${x(row.captured_us)}" y1="${y}" x2="${x(row.captured_us)}" y2="${y+28}" stroke="${color}"><title>Rising ${channel}, sequence ${row.sequence}</title></line>`;continue;}
  let level=null,cursor=start,path='';for(const row of values)if(row.captured_us<start)level=row.high;
  for(const row of visible){const position=x(row.captured_us),next=y+(row.high?0:28);if(level!==null)path+=`M ${x(cursor)} ${y+(level?0:28)} H ${position} V ${next} `;else path+=`M ${position} ${y+(row.high?28:0)} V ${next} `;cursor=row.captured_us;level=row.high;}
  if(level!==null)path+=`M ${x(cursor)} ${y+(level?0:28)} H ${right}`;
  digital+=`<path d="${path}" fill="none" stroke="${color}" stroke-width="1.5"/>`;
 }
 scope.innerHTML=digital;
 const visible=periods.filter(p=>p.time>=start&&p.time<=end),max=Math.max(1,...visible.map(p=>p.period));
 let bars=axis(180);for(const fraction of [0,.5,1])bars+=text(0,145-fraction*120,(max*fraction/1000).toFixed(1)+'ms');
 for(const item of visible){const height=Math.max(2,item.period/max*120),pos=x(item.time),color=!item.period?'var(--red)':median>0&&item.period>median*1.5?'var(--amber)':'var(--green)';bars+=`<line x1="${pos}" x2="${pos}" y1="145" y2="${145-height}" stroke="${color}" stroke-width="2"><title>Sequence ${item.sequence}: ${item.period} µs between rising crank edges</title></line>`;}
 plot.innerHTML=bars;
 $('#trigger-window').textContent=`View ${((start-first)/1000).toFixed(2)} to ${((end-first)/1000).toFixed(2)} ms from first captured edge. ${triggerFrame.includes_falling_edges?'Digital levels start at the first known edge.':'Rising-edge marks only; signal levels are unknown.'}`;
 const reordered=triggerFrame.records.filter((r,i,a)=>i&&r.captured_us<a[i-1].captured_us).length;
 $('#trigger-summary').textContent=`${periods.length} rising crank intervals; median ${median.toFixed(0)} µs; longest ${Math.max(0,...periods.map(p=>p.period)).toFixed(0)} µs; ${periods.filter(p=>!p.period).length} zero intervals. ${reordered} timestamp reversals in callback order. No 720° cam-phase claim.`;
}
function renderTriggerRows(){
 const frame=triggerFrame;if(!frame)return;
 const first=frame.records[0]?.captured_us||0;
 $('#trigger-rows').innerHTML='<table><thead><tr><th>Seq</th><th>Time ms</th><th>Input</th><th>Edge</th><th>Callback µs</th><th>Counter</th><th>Epoch</th></tr></thead><tbody>'+frame.records.map(row=>`<tr><td>${row.sequence}</td><td>${((row.captured_us-first)/1000).toFixed(3)}</td><td>${row.channel}</td><td>${row.high?'rise':'fall'}</td><td>${frame.simulator?'synthetic':row.callback_us-row.captured_us}</td><td>${row.raw_counter??'--'}</td><td>${row.configuration_epoch}</td></tr>`).join('')+'</tbody></table>';
}
function triggerToMsl(frame){
 if(!frame||frame.state==='armed'||!frame.count||frame.records.length!==frame.count)throw Error('Load a complete frozen capture before exporting.');
 const {rows}=triggerSeries(frame),first=rows[0].captured_us;let crank=null,cam=null,previous=null;
 const metadata=(frame.simulator?'COMPLETED SYNTHETIC SIL, RISING CRANK ONLY':'MCU REPORTED DIGITAL CAPTURE, HARDWARE TIMING UNQUALIFIED')+' / '+frame.data_source+' / rows sorted by captured time; Sequence retains callback order';
 const lines=['"ESP32ECU TRIGGER 001"','"'+metadata.replaceAll('"','""')+'"','Time\tCrankEdge\tCamEdge\tCrankLevel\tCamLevel\tToothTime\tCallbackDelay\tRawCounter\tEpoch\tSequence','s\tflag\tflag\tflag\tflag\tus\tus\tticks\t\t'];
 for(const row of rows){let period=null;if(row.channel==='crank'){if(frame.includes_falling_edges)crank=Number(row.high);if(row.high){if(previous!==null)period=row.captured_us-previous;previous=row.captured_us;}}else if(frame.includes_falling_edges)cam=Number(row.high);
  const values=[((row.captured_us-first)/1e6).toFixed(6),row.channel==='crank'?(row.high?1:-1):0,row.channel==='cam'?(row.high?1:-1):0,crank,cam,period,frame.simulator?null:row.callback_us-row.captured_us,row.raw_counter,row.configuration_epoch,row.sequence];lines.push(values.map(v=>v===null?'NaN':v).join('\t'));
 }
 return lines.join('\n')+'\n';
}
window.addEventListener('resize',()=>{if(document.querySelector('#trigger-scope'))drawTriggerCharts()});
