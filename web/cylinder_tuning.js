'use strict';
window.EcuCylinderTuning=(()=>{
 const meta=window.EcuProfileMetadata;
 const defaults=()=>({enabled:false,spark_deg:Array(8).fill(0),fuel_maps:Array.from({length:8},()=>({rpm:[80,800,1600,3000,5000,8000],load:[10,30,50,70,90,110],cells:Array(36).fill(100)}))});
 function constants(t,profiles=true){
  const out=[{page:4,name:'cylinderTrimsEnabled',value:t.cylinder_trims.enabled,flag:true,trimFlag:true}];
  for(let i=0;i<(profiles?8:4);i++){
   out.push({page:4,name:`c${i+1}SparkTrim`,value:t.cylinder_trims.spark_deg[i],trimSpark:i,unit:'deg'});
   for(const [suffix,field]of [['Rpm','rpm'],['Load','load'],['Table','cells']])out.push({page:4,name:`c${i+1}Fuel${suffix}`,value:t.cylinder_trims.fuel_maps[i][field],trimCylinder:i,field,bins:6,unit:field==='rpm'?'RPM':field==='load'?'source_units':'%'});
  }
  return out;
 }
 function validateProfile(t){
  const count=t.engine.cylinders,order=t.timing.firing_order;
  if(!Number.isInteger(count)||count<1||count>8)throw Error('Choose one to eight cylinders.');
  if(!Array.isArray(order)||order.length!==8||order[0]!==1||new Set(order.slice(0,count)).size!==count||order.slice(0,count).some(c=>!Number.isInteger(c)||c<1||c>count)||order.slice(count).some(c=>c!==0))throw Error('Firing order must start with1, include every active cylinder once and leave unused slots zero.');
  if(t.cylinder_trims.spark_deg.length!==8||t.cylinder_trims.fuel_maps.length!==8)throw Error('The current profile requires all eight saved cylinder calibration slots.');
 }
 function configureCount(t,count){
  if(!Number.isInteger(count)||count<1||count>8)throw Error('Choose one to eight cylinders.');
  const order=[1,...new Set(t.timing.firing_order.filter(c=>Number.isInteger(c)&&c>1&&c<=count))];
  for(let c=1;c<=count;c++)if(!order.includes(c))order.push(c);
  t.engine.cylinders=count;t.timing.firing_order=order.concat(Array(8-count).fill(0));
 }
 function migrateFour(t){
  if(t.engine.cylinders!==4||!Number.isFinite(t.engine.displacement_cc)||t.engine.displacement_cc<500||t.engine.displacement_cc>4000||!Number.isFinite(t.engine.injector_cc_min)||t.engine.injector_cc_min<100||t.engine.injector_cc_min>1500)throw Error('Historical identities retain their four-cylinder engine specification limits.');
  const order=t.timing.firing_order.slice(0,4);if(order.length!==4)throw Error('Historical firing order is incomplete.');
  t.timing.firing_order=order.concat([0,0,0,0]);
  const trims=t.cylinder_trims,first=trims.fuel_maps[0];
  trims.spark_deg=trims.spark_deg.slice(0,4).concat([0,0,0,0]);
  trims.fuel_maps=trims.fuel_maps.slice(0,4).concat(Array.from({length:4},()=>({rpm:[...first.rpm],load:[...first.load],cells:Array(36).fill(100)})));
  return t;
 }
 function checkObservation(s){
  const c=s.cylinders,w=s.worker_observation,modern=s.schema_version===3;
  if(!c){if(modern)throw Error('Missing cylinder observation.');return;}
  const count=modern?c.count:4,slots=modern?8:4,mask=modern?255:15;
  const integer=(n,max)=>Number.isInteger(n)&&n>=0&&n<=max;
  if(!integer(count,8)||!Array.isArray(c.proposals)||c.proposals.length!==slots||typeof c.enabled!=='boolean'||['valid_mask','capacity_mask','spark_clamp_mask','retard_floor_mask'].some(k=>!integer(c[k],mask)||(c[k]&~((1<<count)-1))))throw Error('Invalid cylinder observation.');
  for(let i=0;i<slots;i++){
   const p=c.proposals[i],known=Boolean(c.valid_mask&(1<<i));
   if(!p||p.cylinder!==i+1||['pulse_ms','advance_deg','fuel_pct','duty_pct'].some(k=>known?!Number.isFinite(p[k]):modern&&p[k]!==null))throw Error('Invalid cylinder proposal.');
   if(modern&&(p.active!==(i<count)||p.injector_logical_channel!==meta.injector_channels[i]||p.coil_logical_channel!==meta.coil_channels[i]))throw Error('Cylinder identity or channel map changed.');
  }
  if(modern){
   if(!w||!integer(w.cylinder_count,8)||!integer(w.virtual_high_mask,4294967295)||!integer(w.physical_command_mask,255))throw Error('Invalid worker cylinder observation.');
   let allowed=0;for(let i=0;i<w.cylinder_count;i++)allowed|=(1<<meta.injector_channels[i])|(1<<meta.coil_channels[i]);
   let physical=0;for(let i=0;i<Math.min(4,w.cylinder_count);i++)physical|=(1<<meta.injector_channels[i])|(1<<meta.coil_channels[i]);
   if((w.virtual_high_mask&~allowed)||(w.physical_command_mask&~physical))throw Error('Worker masks exceed their own profile or fitted channels.');
   const b=s.board_capacity;if(!b||b.injector_commands!==4||b.coil_commands!==4||b.additional_outputs_allocated!==false)throw Error('Unknown carrier output capacity.');
  }
 }
 function apply(t,item,value){
  if(item.trimFlag)t.cylinder_trims.enabled=value;
  else if(item.trimSpark!==undefined)t.cylinder_trims.spark_deg[item.trimSpark]=value;
  else t.cylinder_trims.fuel_maps[item.trimCylinder][item.field]=value;
 }
 function attach(root,t,changed,toast){
  const trims=t.cylinder_trims;let selected=0;root.dataset.engineCylinderCount=t.engine.cylinders;
  root.innerHTML=`<section class="panel" style="margin-top:20px"><div class="panelhead"><h2>Cylinder adjustments</h2><span class="tag">SEQUENTIAL / OUTPUTS INHIBITED</span></div><div class="panelbody"><label class="check"><input id="cylinder-trims-enabled" type="checkbox" ${trims.enabled?'checked':''}><span>Apply individual fuel and spark trims (sequential mode only)</span></label><p class="hint">Index by cylinder number, independently of firing order. Cylinders1–4 map to J9/J10 channels1–4. Cylinders5–8 have no fitted injector or coil drivers. Extra hardware is required for those outputs. Calibration for inactive cylinders is retained. All outputs remain inhibited.</p><div class="formgrid">${trims.spark_deg.slice(0,t.engine.cylinders).map((v,i)=>`<div class="field"><label for="cylinder-spark-${i+1}">Cylinder ${i+1} spark offset (°BTDC)</label><input id="cylinder-spark-${i+1}" type="number" min="-10" max="10" step="any" value="${v}"></div>`).join('')}</div><p class="hint">Positive offsets advance spark. Trimmed nominal timing is bounded to −5..40° (−5..15° while cranking), then mandatory soft-limit retard is applied. Clamp masks in diagnostics identify constrained cylinders.</p><div class="field"><label for="cylinder-fuel-map">6×6 fuel trim map</label><select id="cylinder-fuel-map">${Array.from({length:t.engine.cylinders},(_,i)=>i+1).map(i=>`<option value="${i-1}">Cylinder ${i} / injector ${i}</option>`).join('')}</select></div><div id="cylinder-fuel-grid" style="margin-top:12px"></div><p class="hint">100% is neutral; 50–150% is allowed. Trims scale effective fuel before adding unchanged injector deadtime once. Disabled trims ignore saved nonneutral values. Each cylinder is checked against pulse and duty limits; one overflow inhibits all channels. An idle/single exhaust wideband cannot identify an individual cylinder imbalance.</p><div id="cylinder-live" class="fine">Waiting for per-cylinder proposals.</div></div></section>`;
  root.querySelector('#cylinder-trims-enabled').onchange=e=>{
   if(e.target.checked&&t.strategy!=='sequential'){e.target.checked=false;toast('Select sequential mode before enabling cylinder trims.',true);return;}
   trims.enabled=e.target.checked;changed();
  };
  trims.spark_deg.slice(0,t.engine.cylinders).forEach((_,i)=>root.querySelector(`#cylinder-spark-${i+1}`).onchange=e=>{trims.spark_deg[i]=Number(e.target.value);changed();});
  const draw=()=>{
   const m=trims.fuel_maps[selected],basis=window.EcuLoadModel.basis(t,'trim'),grid=root.querySelector('#cylinder-fuel-grid');
   grid.innerHTML=`<div class="tablewrap"><table><thead><tr><th>${basis.unit} / RPM</th>${m.rpm.map((v,x)=>`<th><input aria-label="Cylinder ${selected+1} RPM axis ${x+1}" data-trim-axis="rpm" data-index="${x}" type="number" value="${v}" style="width:70px"></th>`).join('')}</tr></thead><tbody>${m.load.map((v,y)=>`<tr><th><input aria-label="Cylinder ${selected+1} load axis ${y+1} ${basis.unit}" data-trim-axis="load" data-index="${y}" min="${basis.min}" max="${basis.max}" type="number" step="any" value="${v}" style="width:70px"></th>${m.rpm.map((_,x)=>`<td><input aria-label="Cylinder ${selected+1} fuel trim row ${y+1} column ${x+1}" data-trim-cell="${y*6+x}" type="number" min="50" max="150" step="any" value="${m.cells[y*6+x]}" style="width:70px"></td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
   grid.querySelectorAll('[data-trim-axis],[data-trim-cell]').forEach(input=>input.onchange=()=>{if(input.dataset.trimAxis)m[input.dataset.trimAxis][Number(input.dataset.index)]=Number(input.value);else m.cells[Number(input.dataset.trimCell)]=Number(input.value);changed();});
  };
  root.querySelector('#cylinder-fuel-map').onchange=e=>{selected=Number(e.target.value);draw();};draw();
 }
 function status(root,c){
  const pane=root.querySelector('#cylinder-live');if(!pane)return;
  if(!c?.available){pane.textContent='Per-cylinder proposals unavailable until qualified inputs and phase permit a completed calculation.';return;}
  const n=v=>Number.isFinite(v)?v.toFixed(3):'unknown';
  pane.innerHTML=`<p>Observation: ${c.count??c.proposals.length} cylinders. ${Number(root.dataset.engineCylinderCount)!==(c.count??c.proposals.length)?'The editor profile differs from this completed observation. ':''}Trims ${c.enabled?'active':'disabled / neutral'} · capacity mask ${c.capacity_mask} · nominal clamp mask ${c.spark_clamp_mask} · retard floor mask ${c.retard_floor_mask}</p><div class="tablewrap"><table><thead><tr><th>CYL</th><th>FUEL %</th><th>PW ms</th><th>ADV °BTDC</th><th>DUTY %</th></tr></thead><tbody>${c.proposals.filter((p,i)=>i<(c.count??c.proposals.length)).map((p,i)=>`<tr><td>${i+1}</td><td>${n(p.fuel_pct)}</td><td>${n(p.pulse_ms)}</td><td>${n(p.advance_deg)}</td><td>${n(p.duty_pct)}</td></tr>`).join('')}</tbody></table></div><p class="hint">Completed controller proposals, not electrical execution. Scalar engine fields and ESP-NOW schema1 retain untrimmed base demand.</p>`;
 }
 return {defaults,constants,apply,attach,status,validateProfile,configureCount,migrateFour,checkObservation,meta};
})();
