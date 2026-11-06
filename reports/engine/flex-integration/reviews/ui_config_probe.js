// Independent Node review, with copied UI modules and no browser/server.
const fs=require('fs'),path=require('path');
const root=path.resolve(process.argv[2]);
global.window={};
eval(fs.readFileSync(path.join(root,'web/flex_fuel.js'),'utf8'));
const base=JSON.parse(fs.readFileSync(path.join(root,'config/engine/defaults.json'),'utf8'));
const edits={
 temp_without_corrections:t=>{t.flex_fuel.correction.temperature_enabled=true;},
 boolean_frequency:t=>{t.flex_fuel.capture.filter_ms=true;},
 string_frequency:t=>{t.flex_fuel.capture.low_hz='50';},
 null_curve:t=>{t.flex_fuel.correction.spark_deg[2]=null;},
 fractional_cycles:t=>{t.flex_fuel.capture.cycles=8.0000001;},
};
const results={};
for(const [name,edit]of Object.entries(edits)){
 const t=structuredClone(base);edit(t);
 try{window.EcuFlexFuel.validateTune(t);results[name]={accepted:true};}
 catch(e){results[name]={accepted:false,error:e.message};}
}
console.log(JSON.stringify({root,mutations:results},null,2));
