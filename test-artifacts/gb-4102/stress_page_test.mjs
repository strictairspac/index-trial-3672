/** Render smoke test for the stress page against a mock worker result.
 * Copies frontend/src to a temp dir (ESM resolution needs a package.json),
 * injects mock store data, renders stressPage and asserts key evidence shows.
 * Run: node test-artifacts/gb-4102/stress_page_test.mjs */
import {mkdtempSync,cpSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
const dir=mkdtempSync(join(tmpdir(),'stress-render-'));
cpSync('/workspace/frontend/src',join(dir,'src'),{recursive:true});
writeFileSync(join(dir,'package.json'),'{"type":"module"}');
const {store}=await import(join(dir,'src/stores/business.js'));
const {stressPage}=await import(join(dir,'src/pages/stress.js'));
const {routes}=await import(join(dir,'src/router/routes.js'));
let fails=0;
const check=(name,cond)=>{console.log(cond?'PASS':'FAIL',name);if(!cond)fails++;};
check('nav route registered',routes.some(r=>r[0]==='stress'&&r[2]==='写入压测'));
const round=(p99,to,late)=>({planned:600,finished:600,p50_ms:4.2,p95_ms:9.8,p99_ms:p99,max_ms:p99*1.4,avg_ms:5.1,avg_queue_wait_ms:0.8,max_queue_wait_ms:p99,timeouts:to,ok:600-to-late,late_success:late,errors:0,pending:0,max_queue_depth:to?23:1,dispatch_max_jitter_ms:1.3,wall_seconds:12.4,backlog:to?{start_ms:3100,end_ms:4900,seconds:1.8}:null,timeline:[[3000,50,to, p99]]});
const recon=to=>({planned:600,dispatched:600,accounted:600,ok:600-to,errors:0,pending:0,late_success:to,late_landed:to,late_tags:['run7-r2-61'],persisted_db:600-to,missing_in_db:0,missing_tags:[],extra_in_db:0,balanced:true,...(to?{ddl_window:{requests:38,accounted:38}}:{})});
store.stress=[{id:7,name:'stress-demo',status:'completed',created_at:'2026-11-18T09:35:00',snapshot:{name:'stress-demo'},
 result:{plan:{requests:600,interval_ms:20,concurrency:8,timeout_ms:500,sample_multiplier:40,ddl_at_ms:3000,columns:['sensor_id','recorded_at']},
 sample:{round_a:{rows:200000,sensor_sum:'10000000',value_sum:'123456.00',id_xor:42},round_b:{rows:200000,sensor_sum:'10000000',value_sum:'123456.00',id_xor:42},same_sample:true},
 rounds:{baseline:round(12.4,0,0),during_ddl:{...round(640.2,57,55),ddl:{index:'stress_candidate',columns:['sensor_id','recorded_at'],started_ms:3000.1,finished_ms:3812.4,duration_ms:812.3}}},
 reconciliation:{baseline:recon(0),during_ddl:recon(57)},
 isolation:{telemetry_rows_before:5000,telemetry_rows_after:5000,untouched:true},
 cleanup:{stress_table_dropped:true,verified_gone:true},
 conclusion:{backlog_seconds:{baseline:0,during_ddl:1.8,extra:1.8},p99_ms:{baseline:12.4,during_ddl:640.2},p95_ms:{baseline:9.8,during_ddl:500.1},timeouts:{baseline:0,during_ddl:57},late_success:{baseline:0,during_ddl:55},accounting_balanced:true},
 summary:'边写边建索引时遥测写入积压约 1.8 秒（不建索引 0 秒）。',
 limitations:['请求到达为开环调度：数据库阻塞不改变到达节奏，延迟从计划到达时刻起算']}}];
const html=stressPage(7);
for(const [name,needle] of [
 ['page heading','边写边建'],['launch form','stress-form'],['run listed','stress-demo'],
 ['backlog metric','积压时长'],['p99 metric','640.2'],['timeout compare','57 笔'],
 ['accounting verdict','无少算'],['ddl window','38 笔请求全部对账'],['late landed','超时后仍落库'],
 ['sample check','两轮起始样本一致'],['isolation','未改动'],['cleanup','已删除并确认'],
 ['conclusion','积压约 1.8 秒'],['export','data-export-stress="7"'],['timeline','窗口起点 ms']])
 check(name,html.includes(needle));
// queued run: no result yet
store.stress.push({id:8,name:'stress-wait',status:'queued',created_at:'2026-11-18T09:40:00',snapshot:{},result:null,error:null});
check('queued run renders waiting note',stressPage(8).includes('后台任务尚未完成'));
// failed run: error surfaced
store.stress.push({id:9,name:'stress-bad',status:'failed',created_at:'2026-11-18T09:41:00',snapshot:{},result:null,error:'建索引失败： Lock wait timeout exceeded'});
check('failed run renders error',stressPage(9).includes('Lock wait timeout'));
// empty store: form still renders, no detail crash
store.stress.length=0;
check('empty store renders form only',stressPage(null).includes('stress-form'));
console.log('---');
console.log(fails?fails+' FAILURES':'ALL PASS');
process.exit(fails?1:0);
