const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const base=__dirname,window={};let checks=0;
vm.runInNewContext(fs.readFileSync(path.join(base,'sources/web/secondary_tables.js'),'utf8'),{window,structuredClone});
function need(ok,why){checks++;if(!ok)throw Error(why);}
function render(e){const hardware={innerHTML:''},pane={innerHTML:'',textContent:''};const root={querySelector:key=>key==='#switch-accessory-status'?hardware:key==='#secondary-observation'?pane:null};window.EcuSecondaryTables.status(root,e);return hardware.innerHTML;}
const host={source:'host_no_target_i2c'},target={source:'target_j4_i2c'};
for(const e of [{},{simulator:false},{simulator:true},{simulator:false,switch_accessory:host},{simulator:true,switch_accessory:target},{switch_accessory:target},{simulator:false,switch_accessory:{source:'other'}}]){
 const html=render(e);need(html.includes('unknown; acquisition diagnostics unavailable'),'missing/contradictory source remains unknown');need(!html.includes('synthetic stimuli only'),'unknown response must not manufacture host provenance');
}
let html=render({simulator:true,switch_accessory:host});need(html.includes('synthetic stimuli only')&&html.includes('host does not measure J4'),'explicit host provenance rendered');
const observed={...target,phase:'reading_inputs',requested_mask:3,fault:'none',last_fault:'i2c_timeout',raw_known:true,fresh:true,ready:true,observed_us:'18446744073709551614',read_completed_us:'18446744073709551615',fault_pending:false,fault_id:'18446744073709551615',reads:'18446744073709551615',failures:'1',consumed_faults:'1',last_duration_us:1620,max_duration_us:1620,budget_us:3000,bus_allocated:true,sdk_error:0};
html=render({simulator:false,switch_accessory:observed});need(html.includes('fresh raw sample')&&html.includes('readback accepted; check each rule below'),'target raw readback is distinct from per-rule qualification');need(html.includes('18446744073709551614 / 18446744073709551615'),'full-width timestamps retained');need(html.includes('separate from electrical and physical qualification'),'digital readback does not qualify electrical hardware');
html=render({simulator:false,switch_accessory:{...observed,fresh:false}});need(html.includes('stale or invalid raw sample'),'age invalidity is explicit');
html=render({simulator:false,switch_accessory:{...observed,phase:'<img src=x onerror=attack()>',fault:'<script>attack()</script>',ready:false,fault_pending:true}});need(!html.includes('<img')&&!html.includes('<script>')&&html.includes('&lt;script&gt;'),'diagnostic text escaped');need(html.includes('yes, ID 18446744073709551615'),'full-width pending fault identity retained');
console.log(JSON.stringify({passed:true,ui_assertions:checks,execution:'Node VM with minimal DOM assignment fixture; no browser/physical acceptance'}));
