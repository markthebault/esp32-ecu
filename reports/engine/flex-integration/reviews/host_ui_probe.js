// Independent copied-module tests. No DOM, network, browser, or service.
const fs=require('fs'),path=require('path');
const root=path.resolve(process.argv[2]),out=path.resolve(process.argv[3]);
global.window={};
for(const f of ['cylinder_tuning.js','idle_control.js','transient_enrichment.js','load_model.js','secondary_tables.js','flex_fuel.js']){
 const p=path.join(root,'web',f);if(fs.existsSync(p))eval(fs.readFileSync(p,'utf8'));
}
let checks=0;const requireTrue=(v,m)=>{++checks;if(!v)throw Error(m);};
const rejected=(fn,m)=>{try{fn();}catch(e){++checks;return;}throw Error('accepted '+m);};
const base=JSON.parse(fs.readFileSync(path.join(root,'config/engine/defaults.json'),'utf8'));
let html=fs.readFileSync(path.join(root,'web/index.html'),'utf8');
const block=html.slice(html.indexOf('const LEGACY_ENGINE_SIGNATURE='),html.indexOf('function engineCycleSummary'));
eval(block+'\nglobalThis.reviewFunctions={engineImportShape,upgradeLegacyEngine,engineCapabilities};');
for(let schema=1;schema<=8;++schema){
 let t=JSON.parse(fs.readFileSync(path.join(root,'config/engine/defaults-v'+Math.max(2,schema)+'.json'),'utf8'));
 if(schema===1){t.schema_version=1;delete t.timing;}
 if(schema===8){t.secondary_tables.fuel.map.cells[7]=93.25;t.secondary_tables.spark.map.cells[15]=-3.125;}
 const old=structuredClone(t),u=reviewFunctions.upgradeLegacyEngine(t,base);
 reviewFunctions.engineImportShape(u,base);
 requireTrue(u.schema_version===9&&JSON.stringify(u.flex_fuel)===JSON.stringify(window.EcuFlexFuel.defaults()),'neutral migration '+schema);
 if(schema===8)requireTrue(JSON.stringify(u.secondary_tables)===JSON.stringify(old.secondary_tables),'all schema8 secondary preserved');
}
for(const mutation of [t=>{delete t.flex_fuel;},t=>{t.flex_fuel.capture.filter_ms='1';},t=>{t.flex_fuel.correction.enabled=1;},t=>{t.flex_fuel.extra=0;},t=>{t.flex_fuel.correction.fuel_pct.pop();}]){
 let t=structuredClone(base);mutation(t);rejected(()=>reviewFunctions.engineImportShape(t,base),'strict imported shape');
}
requireTrue(reviewFunctions.engineCapabilities('ESP32ECU DEV 009 INHIBITED').secondary&&!reviewFunctions.engineCapabilities('ESP32ECU DEV 009 INHIBITED').flex,'009 retains only old fields');
requireTrue(reviewFunctions.engineCapabilities('ESP32ECU DEV 010 INHIBITED').flex&&!reviewFunctions.engineCapabilities('Speeduino').known,'010 identity exact');
const fixtures=JSON.parse(fs.readFileSync(path.join(out,'host-diagnostic-fixtures.json'),'utf8'));
window.EcuFlexFuel.checkObservation(fixtures.sample.flex_fuel,true);++checks;
const values=window.EcuFlexFuel.logValues(fixtures.sample),fields=window.EcuFlexFuel.logFields.map(r=>r[0]);
requireTrue(values[fields.indexOf('FlexRawEdges')]==='18446744073709551615'&&values[fields.indexOf('FlexFaultGeneration')]==='9007199254740993','browser export retains U64 strings');
const mutations=JSON.parse(fs.readFileSync(path.join(out,'host-diagnostic-mutations.json'),'utf8')),differential={};
for(const [name,v]of Object.entries(mutations)){
 let accepted=true,error='';try{window.EcuFlexFuel.checkObservation(v.flex,true);}catch(e){accepted=false;error=e.message;}
 differential[name]={native_accepted:v.native_accepted,browser_accepted:accepted,error};
}
eval(fs.readFileSync(path.join(root,'web/engine_logger.js'),'utf8'));
const logger=window.EcuEngineLogger;
logger.adopt(fixtures.header);
for(const p of fixtures.pages)logger.acceptPage(p);
requireTrue(logger.inspect().rows===128&&logger.inspect().cursor===300&&JSON.stringify(logger.inspect().gaps)==='[[1,172]]','browser retained rows/loss accounting');
const exported=logger.exportMsl(),lines=exported.trimEnd().split('\n').map(l=>l.replace(/\r$/,'').split('\t'));
requireTrue(lines[2].length===229&&lines.slice(3).every(l=>l.length===229),'browser MSL 229 columns');
requireTrue(lines[4][lines[2].indexOf('FlexRawEdges')]==='18446744073709551615','browser MSL exact U64');
logger.adopt(fixtures.header);
const malformed=structuredClone(fixtures.pages[0]);malformed.records[1].sample.flex_fuel.raw_edges='18446744073709551616';
rejected(()=>logger.acceptPage(malformed),'whole malformed page');
requireTrue(logger.inspect().rows===0&&logger.inspect().cursor===0&&logger.inspect().gaps.length===0,'page validation atomic');
let pane={innerHTML:'',textContent:''};let rootElement={querySelector:()=>pane};
window.EcuFlexFuel.status(rootElement,{simulator:true,flex_fuel:fixtures.sample.flex_fuel});
requireTrue(pane.innerHTML.includes('synthetic_edges / completed synthetic run')&&pane.innerHTML.includes('raw capture qualified'),'honest raw source label');
const scalar=structuredClone(fixtures.sample.flex_fuel);Object.assign(scalar,{source:'synthetic_value',value_qualified:true,raw_capture_qualified:false,frequency_hz:null,low_pulse_us:null,fuel_temp_c:null});
window.EcuFlexFuel.status(rootElement,{simulator:true,flex_fuel:scalar});
requireTrue(pane.innerHTML.includes('synthetic percentage only')&&pane.innerHTML.includes('unknown Hz / unknown us'),'scalar waveform unknown');
const configCases=JSON.parse(fs.readFileSync(path.join(out,'host-config-cases.json'),'utf8')),configDifferential=[];
for(const c of configCases){let accepted=true;try{window.EcuFlexFuel.validateTune(c.tune);}catch(e){accepted=false;}++checks;if(accepted!==c.native_accepted)configDifferential.push({name:c.name,native_accepted:c.native_accepted,browser_accepted:accepted});}
console.log(JSON.stringify({passed:true,checks,diagnostic_differential:differential,configuration_differential:configDifferential},null,2));
