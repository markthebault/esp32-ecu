const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const own=path.resolve(__dirname,'..'),html=fs.readFileSync(path.join(own,'freeze-ui-recheck-001/web/index.html'),'utf8');
const start=html.indexOf('function radioLinkText('),end=html.indexOf('function renderScreens(',start);assert(start>=0&&end>start);
const context={};vm.createContext(context);vm.runInContext(html.slice(start,end)+'\nthis.link=radioLinkText;this.engine=radioEnginePeerText;',context);
let checks=0;function check(x){checks++;assert(x);}
const good={engine_telemetry:true,engine_schema:5,engine_connected:true,last_engine_ack_ms:0,engine_parts_per_observation:2,engine_pair_pending:false,engine_base_submitted:false};
check(context.engine(good).includes('complete engine observation ACK 0 ms ago'));
const missing={...good,engine_connected:false,last_engine_ack_ms:-1,engine_pair_pending:true,engine_base_submitted:true};check(context.engine(missing).includes('no complete engine observation acknowledged'));check(context.engine(missing).includes('base submitted, flex submission pending'));
for(const [key,value]of [['engine_telemetry','true'],['engine_schema',6],['engine_schema',4.5],['engine_connected','true'],['last_engine_ack_ms',-1],['last_engine_ack_ms',3000],['last_engine_ack_ms',0.5],['last_engine_ack_ms',NaN],['last_engine_ack_ms',Infinity],['last_engine_ack_ms',2**53],['engine_parts_per_observation',1],['engine_pair_pending',1],['engine_base_submitted','false']])check(context.engine({...good,[key]:value})==='Engine observation ACK status unknown');
check(context.engine({...missing,last_engine_ack_ms:100})==='Engine observation ACK status unknown');check(context.engine({...good,engine_base_submitted:true})==='Engine observation ACK status unknown');
check(context.engine({...good,engine_schema:4,engine_parts_per_observation:1,engine_pair_pending:true})==='Engine observation ACK status unknown');
check(context.engine({...good,engine_connected:false,last_engine_ack_ms:3000}).includes('ACK is stale'));
check(context.engine({engine_telemetry:false})==='legacy sensor stream');check(context.engine({})==='Engine observation ACK status unknown');
check(context.link({connected:true,last_ack_ms:2999})==='Link connected');check(context.link({connected:true,last_ack_ms:3000})==='Link acknowledgement unknown');check(context.link({connected:'true',last_ack_ms:0})==='Link status unknown');
const fixtures=path.join(own,'sender-001/fixtures');let native=0;
for(const name of ['partial','complete','held-expired','engine-ack-missing']){const f=path.join(fixtures,name+'.json');if(!fs.existsSync(f))continue;const data=JSON.parse(fs.readFileSync(f));check(Array.isArray(data.peers)&&data.peers.length===1);const text=context.engine(data.peers[0]);check(!text.includes('status unknown'));if(name==='partial')check(text.includes('no complete engine observation acknowledged'));if(name==='complete')check(text.includes('complete engine observation ACK'));native++;}
console.log(JSON.stringify({passed:true,checks,native_fixture_states:native,scope:'Pure functions extracted from frozen browser source; no browser, RF, firmware, GPIO or I2C execution'}));
