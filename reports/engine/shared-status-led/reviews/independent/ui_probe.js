'use strict';
const fs=require('fs'),path=require('path'),crypto=require('crypto'),vm=require('vm');
const base=__dirname,freeze=path.join(base,process.argv[2]||'freeze-002');
const html=fs.readFileSync(path.join(freeze,'web/index.html'),'utf8');
const start=html.indexOf('function radioIndicatorText('),end=html.indexOf('\n}',start)+2;
if(start<0||end<start)throw Error('function boundary');
const code=html.slice(start,end); const context={};vm.createContext(context);vm.runInContext(code,context);
const render=x=>context.radioIndicatorText(x); let checks=0;const outputs=[];
function check(ok,label){checks++;if(!ok)throw Error(label);}
const fixtures=path.join(base,process.argv[3]||'ui-fixtures-001');
const names=fs.readdirSync(fixtures).filter(n=>n.endsWith('.json'));
for(const name of names){const indicator=JSON.parse(fs.readFileSync(path.join(fixtures,name),'utf8'));
 const text=render({simulator:false,indicator,led:'green'});outputs.push({fixture:name,text});
 check(text.includes('unproven.'),name+' advisory');
 check(text.includes(indicator.ready?'Expander latch verified green':'Historical latch: green'),name+' verified state');
 check(!/healthy|CPU running|light verified/.test(text),name+' no false health');}
const original=JSON.parse(fs.readFileSync(path.join(fixtures,'green_ready.json'),'utf8'));
function altered(edit){const i=structuredClone(original);edit(i);return render({simulator:false,indicator:i,led:'green'});}
function unknown(edit,label){const t=altered(edit);check(t.startsWith('LED readback is unknown or inconsistent.'),label);}
for(const v of ['__proto__','constructor','toString',null,{},0,'Green']){
 unknown(i=>i.requested_pattern=v,'bad request '+String(v));unknown(i=>i.serviced_pattern=v,'bad serviced '+String(v));}
for(const k of ['known','fresh','ready','device_allocated'])unknown(i=>i[k]=1,k+' boolean');
for(const n of [NaN,Infinity,1.2,2147483648,-2147483649,'0',null])unknown(i=>i.sdk_error=n,'bad SDK '+n);
for(const k of ['observed_us','read_completed_us','snapshot_us']){
 for(const n of ['','-1','01','1.0','18446744073709551616',0,null])unknown(i=>i[k]=n,k+' malformed '+n);}
unknown(i=>i.observed_us=(BigInt(i.read_completed_us)+1n).toString(),'observed after completion');
unknown(i=>i.read_completed_us=(BigInt(i.snapshot_us)+1n).toString(),'completion after snapshot');
unknown(i=>i.snapshot_us=(BigInt(i.observed_us)+250001n).toString(),'fresh past age');
for(const k of ['last_verified_latch','last_written_rgb','requested_rgb']){
 for(const n of [3,7,-1,8,'2',null])unknown(i=>i[k]=n,k+' invalid '+n);}
unknown(i=>i.fault='configuration_mismatch','ready plus fault');
unknown(i=>i.phase='retry_wait','ready wrong phase');
unknown(i=>i.fresh=false,'ready stale');
unknown(i=>i.device_allocated=false,'ready no handle');
unknown(i=>i.sdk_error=-1,'ready failed SDK');
unknown(i=>i.requested_pattern='off','ready pending pattern');
unknown(i=>i.last_verified_latch=0,'ready latch mismatch');
unknown(i=>i.requested_rgb=4,'ready target mismatch');
unknown(i=>i.contract='other','wrong contract');
const big=altered(i=>{i.observed_us='18446744073709251615';i.read_completed_us='18446744073709251616';i.snapshot_us='18446744073709501615';});
check(big.includes('250.0 ms old.')&&big.includes('Expander latch verified'),'exact U64 boundary accepted');
const old=altered(i=>{i.fresh=false;i.ready=false;i.snapshot_us='18446744073709551615';i.sdk_error=-1; i.fault='i2c_other';});
check(old.includes('Historical latch: green')&&old.includes('SDK -1')&&!old.includes('Expander latch verified'),'old signed fault advisory');
check(altered(i=>i.known=false).includes('Latch unknown.'),'unknown retained');
check(render({simulator:true,indicator:original,led:'green'}).includes('Host fixture'),'host not physical');
check(render({indicator:original,led:'green'}).includes('not measured'),'missing provenance');
check(render({simulator:false,led:'green'}).includes('Hardware readback is unavailable'),'legacy no readback');
check(render({simulator:false,led:'__proto__'}).startsWith('Requested policy: unknown'),'legacy hostile enum');
check(html.includes('requested/advisory')||html.includes('Requested/advisory')||html.includes('Requested policy'),'policy description');
const failBlock=html.slice(html.indexOf('async function refreshRadio'),html.indexOf('async function refreshRadio')+6000);
check(failBlock.includes('LED readback unavailable')||failBlock.includes('readback unavailable'),'failed poll clears health');
const report={passed:true,checks,source_sha256:crypto.createHash('sha256').update(html).digest('hex'),function_sha256:crypto.createHash('sha256').update(code).digest('hex'),outputs,scope:'Pure extracted JavaScript validator plus native fake-SDK service fixtures; no browser, device, service or hardware execution.'};
fs.writeFileSync(path.join(base,'ui-probe-'+(process.argv[4]||'001')+'.json'),JSON.stringify(report,null,2)+'\n');process.stdout.write(JSON.stringify({passed:true,checks})+'\n');
