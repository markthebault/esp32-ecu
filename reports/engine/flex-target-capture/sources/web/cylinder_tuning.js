'use strict';
window.EcuCylinderTuning=(()=>{
 const defaults=()=>({enabled:false,spark_deg:[0,0,0,0],fuel_maps:Array.from({length:4},()=>({rpm:[80,800,1600,3000,5000,8000],load:[10,30,50,70,90,110],cells:Array(36).fill(100)}))});
 function constants(t){
  const out=[{page:4,name:'cylinderTrimsEnabled',value:t.cylinder_trims.enabled,flag:true,trimFlag:true}];
  for(let i=0;i<4;i++){
   out.push({page:4,name:`c${i+1}SparkTrim`,value:t.cylinder_trims.spark_deg[i],trimSpark:i,unit:'deg'});
   for(const [suffix,field]of [['Rpm','rpm'],['Load','load'],['Table','cells']])out.push({page:4,name:`c${i+1}Fuel${suffix}`,value:t.cylinder_trims.fuel_maps[i][field],trimCylinder:i,field,bins:6,unit:field==='rpm'?'RPM':field==='load'?'source_units':'%'});
  }
  return out;
 }
 function apply(t,item,value){
  if(item.trimFlag)t.cylinder_trims.enabled=value;
  else if(item.trimSpark!==undefined)t.cylinder_trims.spark_deg[item.trimSpark]=value;
  else t.cylinder_trims.fuel_maps[item.trimCylinder][item.field]=value;
 }
 function attach(root,t,changed,toast){
  const trims=t.cylinder_trims;let selected=0;
  root.innerHTML=`<section class="panel" style="margin-top:20px"><div class="panelhead"><h2>Physical cylinder adjustments</h2><span class="tag">SEQUENTIAL / OUTPUTS INHIBITED</span></div><div class="panelbody"><label class="check"><input id="cylinder-trims-enabled" type="checkbox" ${trims.enabled?'checked':''}><span>Apply individual fuel and spark trims (sequential mode only)</span></label><p class="hint">Index by physical cylinders 1–4, independently of firing order. INJ1/IGN1 belong to cylinder 1, through INJ4/IGN4 for cylinder 4. J9 pins 1–4 are injector channels 1–4; J10 pins 1–4 are the smart-coil logic channels. Verify the harness and compression TDC independently. Outputs stay inhibited.</p><div class="formgrid">${trims.spark_deg.map((v,i)=>`<div class="field"><label for="cylinder-spark-${i+1}">Cylinder ${i+1} spark offset (°BTDC)</label><input id="cylinder-spark-${i+1}" type="number" min="-10" max="10" step="any" value="${v}"></div>`).join('')}</div><p class="hint">Positive offsets advance spark. Trimmed nominal timing is bounded to −5..40° (−5..15° while cranking), then mandatory soft-limit retard is applied. Clamp masks in diagnostics identify constrained cylinders.</p><div class="field"><label for="cylinder-fuel-map">6×6 fuel trim map</label><select id="cylinder-fuel-map">${[1,2,3,4].map(i=>`<option value="${i-1}">Cylinder ${i} / injector ${i}</option>`).join('')}</select></div><div id="cylinder-fuel-grid" style="margin-top:12px"></div><p class="hint">100% is neutral; 50–150% is allowed. Trims scale effective fuel before adding unchanged injector deadtime once. Disabled trims ignore saved nonneutral values. Each cylinder is checked against pulse and duty limits; one overflow inhibits all channels. An idle/single exhaust wideband cannot identify an individual cylinder imbalance.</p><div id="cylinder-live" class="fine">Waiting for per-cylinder proposals.</div></div></section>`;
  root.querySelector('#cylinder-trims-enabled').onchange=e=>{
   if(e.target.checked&&t.strategy!=='sequential_4cyl'){e.target.checked=false;toast('Select sequential mode before enabling cylinder trims.',true);return;}
   trims.enabled=e.target.checked;changed();
  };
  trims.spark_deg.forEach((_,i)=>root.querySelector(`#cylinder-spark-${i+1}`).onchange=e=>{trims.spark_deg[i]=Number(e.target.value);changed();});
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
  pane.innerHTML=`<p>Trims ${c.enabled?'active':'disabled / neutral'} · capacity mask ${c.capacity_mask} · nominal clamp mask ${c.spark_clamp_mask} · retard floor mask ${c.retard_floor_mask}</p><div class="tablewrap"><table><thead><tr><th>CYL</th><th>FUEL %</th><th>PW ms</th><th>ADV °BTDC</th><th>DUTY %</th></tr></thead><tbody>${c.proposals.map((p,i)=>`<tr><td>${i+1}</td><td>${n(p.fuel_pct)}</td><td>${n(p.pulse_ms)}</td><td>${n(p.advance_deg)}</td><td>${n(p.duty_pct)}</td></tr>`).join('')}</tbody></table></div><p class="hint">Completed controller proposals, not electrical execution. Scalar engine fields and ESP-NOW schema1 retain untrimmed base demand.</p>`;
 }
 return {defaults,constants,apply,attach,status};
})();
