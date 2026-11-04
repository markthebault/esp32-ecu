'use strict';
const fs=require('fs'),path=require('path'),vm=require('vm'),crypto=require('crypto');
const own=__dirname,freeze=path.join(own,process.argv[2]||'freeze-003'),run=process.argv[3]||'001';
const source=fs.readFileSync(path.join(freeze,'web/flex_fuel.js'),'utf8');
const context={window:{},structuredClone};vm.createContext(context);vm.runInContext(source,context);const render=(d,simulator=false)=>context.window.EcuFlexFuel.captureText(d,simulator);
const dir=path.join(own,process.argv[4]||'actual-service-001/fixtures-0');const base=JSON.parse(fs.readFileSync(path.join(dir,'qualified.json'),'utf8')).flex_capture;
const outcomes=[],checks=[];function check(ok,label){checks.push({label,ok});}
for(const file of fs.readdirSync(dir).filter(n=>n.endsWith('.json'))){const d=JSON.parse(fs.readFileSync(path.join(dir,file),'utf8')).flex_capture;const text=render(d);const expected=d.publication.qualified&&d.publication.current&&(BigInt(d.query_us)-BigInt(d.publication.published_us)<=50000n);check(text.includes('publication is current.')===expected,'native fixture '+file);outcomes.push({fixture:file,text});}
const cases=[
 ['nonready_reason',d=>d.publication.reason='stale'],['nonready_capture_reason',d=>d.publication.capture_reason='low_pulse_width_out_of_range'],
 ['failed_SDK',d=>d.driver_error='ESP_ERR_INVALID_STATE'],['unacknowledged_ingress',d=>{d.fault_generation='1';d.publication.ingress_generation='1';d.acknowledged_generation='0';}],
 ['zero_context',d=>d.context=d.publication.context='0'],['zero_tune_revision',d=>d.requested_tune_revision=d.publication.producer_tune_revision=0],['zero_sensor_revision',d=>d.requested_sensor_revision=0],['zero_clock_uncertainty',d=>d.clock_uncertainty_us=0],
 ['synthetic_source',d=>d.publication.source='synthetic_edges'],['unknown_reason',d=>d.publication.reason='not_a_reason'],['future_publication',d=>d.publication.published_us=(BigInt(d.query_us)+1n).toString()],['future_sample',d=>d.publication.sample_us=(BigInt(d.query_us)+1n).toString()],
 ['expiry_extension',d=>d.publication.valid_until_us=(BigInt(d.publication.valid_until_us)+1n).toString()],['wrong_calibration',d=>d.publication.producer_calibration.low_hz=40],['bad_calibration_type',d=>d.publication.producer_calibration.low_hz='50'],['missing_calibration',d=>d.publication.producer_calibration=null],
 ['stale_publication',d=>d.query_us=(BigInt(d.publication.published_us)+50001n).toString()],['ready_but_pending_capture',d=>d.publication.pending_fault=true],['ready_but_pending_ingress',d=>d.pending_fault=true],['acknowledge_future_generation',d=>d.publication.acknowledged_generation='18446744073709551615'],
 ['ready_but_not_active',d=>d.active=false],['numeric_U64',d=>d.query_us=Number(d.query_us)],['leading_zero',d=>d.context='01'],['overflow_U64',d=>d.query_us='18446744073709551616']
];
if(base.minimum_command_publication!==undefined)cases.push(['revoked_publication',d=>d.minimum_command_publication=(BigInt(d.publication.sequence)+1n).toString()],['invalid_publication_floor',d=>d.minimum_command_publication='18446744073709551616']);
for(const [name,mutate]of cases){const d=structuredClone(base);mutate(d);const text=render(d);const rejected=!text.includes('publication is current.');check(rejected,'malformed '+name);outcomes.push({case:name,rejected,text});}
check(render(base,true).includes('no target GPIO38 capture is measured'),'host not measured');check(render(null).includes('unavailable'),'missing capture unavailable');
const report={passed:checks.every(x=>x.ok),checks:checks.length,source_sha256:crypto.createHash('sha256').update(source).digest('hex'),checks_detail:checks,outcomes,scope:'Pure current-capture validator on own actual-service SDK-model captures. No browser, service or hardware execution.'};fs.writeFileSync(path.join(own,'ui-capture-'+run+'.json'),JSON.stringify(report,null,2)+'\n');process.stdout.write(JSON.stringify({passed:report.passed,checks:report.checks,failed:checks.filter(x=>!x.ok).map(x=>x.label)})+'\n');
