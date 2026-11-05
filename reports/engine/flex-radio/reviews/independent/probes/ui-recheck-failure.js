// Execute frozen refreshRadio() in an in-memory DOM/API model; no HTTP service.
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const own=path.resolve(__dirname,'..'),html=fs.readFileSync(path.join(own,'freeze-ui-recheck-001/web/index.html'),'utf8');
const helperStart=html.indexOf('function radioIndicatorText('),helperEnd=html.indexOf('function renderScreens(',helperStart),refreshStart=html.indexOf('async function refreshRadio('),refreshEnd=html.indexOf('function renderDevice(',refreshStart);assert(helperStart>=0&&helperEnd>helperStart&&refreshStart>=0&&refreshEnd>refreshStart);
const nodes=new Map();function node(id){if(!nodes.has(id))nodes.set(id,{textContent:'',innerHTML:'',disabled:false,classes:new Set(),classList:{add(k){nodes.get(id).classes.add(k)},toggle(k,value){if(value)nodes.get(id).classes.add(k);else nodes.get(id).classes.delete(k)}}});return nodes.get(id);}
let checks=0;function check(x){checks++;assert(x);}
let scheduled=0;const context={current:'screens',radioState:null,radioTimer:1,clearTimeout(){},setTimeout(fn,ms){check(ms===500);scheduled++;return scheduled;},document:{querySelectorAll(){return[];}},$(selector){return node(selector.slice(1));},set(id,value){node(id).textContent=String(value);},esc(value){return String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');},num(value,n=2){return Number.isFinite(value)?value.toFixed(n):'--';}};
vm.createContext(context);vm.runInContext(html.slice(helperStart,helperEnd)+'\n'+html.slice(refreshStart,refreshEnd),context);
(async()=>{
 const source=JSON.parse(fs.readFileSync(path.join(own,'sender-001/fixtures/complete.json'),'utf8'));context.api=async()=>structuredClone(source);await context.refreshRadio();
 check(node('radio-engine-status').textContent.includes('Engine source:'));check(node('radio-peers').innerHTML.includes('Link connected'));check(node('radio-peers').innerHTML.includes('complete engine observation ACK '));
 context.api=async()=>{throw Error('Owned offline probe');};await context.refreshRadio();
 check(node('radio-engine-status').textContent.includes('unknown'));check(!node('radio-engine-status').textContent.includes('Engine source:'));check(node('radio-peers').innerHTML.includes('unknown'));check(!node('radio-peers').innerHTML.includes('Link connected'));check(!node('radio-peers').innerHTML.includes('complete engine observation ACK '));check(!node('radio-peers').innerHTML.includes('ms ago'));
 check(node('radio-indicator-status').textContent.includes('unavailable'));check(node('pair-open').disabled&&node('pair-cancel').disabled);check(node('pair-candidate').innerHTML==='');check(node('pair-details').classes.has('hidden'));check(node('pair-key').textContent==='');check(scheduled===2);
 // A failed in-flight request must not overwrite another page or rearm polling.
 node('radio-engine-status').textContent='Other-page sentinel';node('radio-peers').innerHTML='Other-page peers';context.current='screens';context.api=async()=>{context.current='engine';throw Error('Page changed in flight');};await context.refreshRadio();check(node('radio-engine-status').textContent==='Other-page sentinel');check(node('radio-peers').innerHTML==='Other-page peers');check(scheduled===2);
 // A recovered request can display new positive observations again.
 context.current='screens';context.api=async()=>structuredClone(source);await context.refreshRadio();check(node('radio-peers').innerHTML.includes('complete engine observation ACK '));check(node('radio-engine-status').textContent.includes('Engine source:'));check(scheduled===3);
 console.log(JSON.stringify({accepted:true,checks,transitions:['complete_to_HTTP_failure','page_changed_during_failed_request','fresh_success_after_failure'],scope:'Actual frozen refreshRadio and helpers in an in-memory DOM/API model; no browser, server, device or RF'}));
})().catch(e=>{console.error(e);process.exitCode=1;});
