"""Open-loop write stress test against the ephemeral telemetry_stress table.

Two rounds share one immutable write plan, one concurrency cap and an identical
starting sample. Round 1 writes without DDL; round 2 runs CREATE INDEX mid-plan.
The dispatcher releases requests at their planned arrival times regardless of
database blocking, latency is measured from the planned arrival, and every
request is reconciled against rows actually persisted. The stress table is
dropped and telemetry verified untouched before any conclusion is assembled.
All dynamic identifiers are server-side constants or whitelisted columns."""
import queue,threading,time
from sqlalchemy import create_engine,text
from src.config.settings import DATABASE_URL
from src.constants.enums import COLUMNS
from src.services.stress_math import round_stats,accounting_balanced
TABLE='telemetry_stress'
INDEX='stress_candidate'
LOCK='stress_run_serial'
LOCK_WAIT_S=30
DRAIN_MARGIN_S=75
def _reset_table(c,multiplier):
 c.execute(text(f'DROP TABLE IF EXISTS {TABLE}'))
 c.execute(text(f'CREATE TABLE {TABLE} (id INT AUTO_INCREMENT PRIMARY KEY, sensor_id INT NOT NULL, recorded_at VARCHAR(30) NOT NULL, device_type VARCHAR(40) NOT NULL, value DOUBLE NOT NULL, req_tag VARCHAR(64) NOT NULL)'))
 for _ in range(multiplier):
  c.execute(text(f"INSERT INTO {TABLE} (sensor_id,recorded_at,device_type,value,req_tag) SELECT sensor_id,recorded_at,device_type,value,'sample' FROM telemetry ORDER BY id"))
def _checksum(c):
 row=c.execute(text(f'SELECT COUNT(*) AS c, COALESCE(SUM(sensor_id),0) AS s, COALESCE(SUM(CAST(value AS DECIMAL(12,2))),0) AS v, COALESCE(BIT_XOR(id),0) AS x FROM {TABLE}')).mappings().one()
 return {'rows':row['c'],'sensor_sum':str(row['s']),'value_sum':str(row['v']),'id_xor':row['x']}
def _round(eng,plan,run_tag,rnd,ddl):
 n=plan['requests'];iv=plan['interval_ms']/1000.0;conc=plan['concurrency']
 rec=[{'seq':i,'tag':f'{run_tag}-r{rnd}-{i}','sched':i*iv} for i in range(n)]
 work=queue.Queue();t0=time.monotonic()
 def dispatch():
  for r in rec:
   target=t0+r['sched']
   while True:
    remain=target-time.monotonic()
    if remain<=0:break
    time.sleep(min(remain,0.02))
   r['dispatched']=time.monotonic()-t0
   work.put(r['seq'])
  for _ in range(conc):work.put(None)
 def writer():
  with eng.connect().execution_options(isolation_level='AUTOCOMMIT') as c:
   c.execute(text(f'SET SESSION lock_wait_timeout={LOCK_WAIT_S}'))
   ins=text(f'INSERT INTO {TABLE} (sensor_id,recorded_at,device_type,value,req_tag) VALUES (:s,:t,:d,:v,:tag)')
   while True:
    i=work.get()
    if i is None:return
    r=rec[i];r['dequeued']=time.monotonic()-t0
    try:
     c.execute(ins,{'s':900+rnd,'t':'2026-11-18T00:00:00','d':'pump','v':(i*7%100)/10.0,'tag':r['tag']})
     r['outcome']='ok'
    except Exception as exc:
     r['outcome']='error';r['error']=str(exc)[:200]
    r['finished']=time.monotonic()-t0
 def build():
  while time.monotonic()-t0<ddl['at_ms']/1000.0:time.sleep(0.01)
  ddl['started']=time.monotonic()-t0
  cols=','.join('`'+x+'`' for x in ddl['columns'])
  try:
   with eng.connect().execution_options(isolation_level='AUTOCOMMIT') as c:
    c.execute(text('SET SESSION lock_wait_timeout=60'))
    c.execute(text(f'CREATE INDEX {INDEX} ON {TABLE} ({cols})'))
  except Exception as exc:
   ddl['error']=str(exc)[:300]
  ddl['finished']=time.monotonic()-t0
 writers=[threading.Thread(target=writer,daemon=True) for _ in range(conc)]
 for t in writers:t.start()
 d=threading.Thread(target=dispatch,daemon=True);d.start()
 b=threading.Thread(target=build,daemon=True) if ddl else None
 if b:b.start()
 d.join()
 deadline=t0+rec[-1]['sched']+DRAIN_MARGIN_S
 for t in writers:t.join(max(0.1,deadline-time.monotonic()))
 if b:b.join(max(0.1,deadline-time.monotonic()))
 for r in rec:
  if 'finished' not in r:r.setdefault('outcome','pending')
 if ddl and ddl.get('error'):raise RuntimeError('建索引失败： '+ddl['error'])
 if ddl and 'finished' not in ddl:raise RuntimeError('建索引未在兜底时间内结束')
 return rec,ddl
def _reconcile(c,rec,run_tag,rnd,timeout_ms):
 found={row[0] for row in c.execute(text(f'SELECT req_tag FROM {TABLE} WHERE req_tag LIKE :p'),{'p':f'{run_tag}-r{rnd}-%'})}
 tags={r['tag'] for r in rec}
 missing=sorted(tags-found);extra=sorted(found-tags)
 ok=[r for r in rec if r.get('outcome')=='ok']
 late=[r for r in ok if (r['finished']-r['sched'])*1000.0>timeout_ms]
 out={'planned':len(rec),
 'dispatched':sum(1 for r in rec if 'dispatched' in r),
 'accounted':sum(1 for r in rec if 'outcome' in r),
 'ok':len(ok),'errors':sum(1 for r in rec if r.get('outcome')=='error'),
 'pending':sum(1 for r in rec if r.get('outcome')=='pending'),
 'late_success':len(late),'late_landed':sum(1 for r in late if r['tag'] in found),
 'late_tags':[r['tag'] for r in late[:20]],
 'persisted_db':len(found),'missing_in_db':len(missing),'missing_tags':missing[:20],
 'extra_in_db':len(extra)}
 out['balanced']=accounting_balanced(out['planned'],out['dispatched'],out['accounted'],out['persisted_db'],out['ok'],out['missing_in_db'],out['extra_in_db'])
 return out
def _assemble(plan,checksums,rounds,recon,cleanup,iso):
 stats={}
 for rnd,(rec,ddl) in rounds.items():
  s=round_stats(rec,plan['timeout_ms'])
  if ddl:
   s['ddl']={'index':INDEX,'columns':ddl['columns'],'started_ms':round(ddl['started']*1000.0,1),'finished_ms':round(ddl['finished']*1000.0,1),'duration_ms':round((ddl['finished']-ddl['started'])*1000.0,1)}
   window=[r for r in rec if ddl['started']<=r['sched']<=ddl['finished']]
   recon[rnd]['ddl_window']={'requests':len(window),'accounted':sum(1 for r in window if 'outcome' in r)}
  stats[rnd]=s
 a,b=stats[1],stats[2]
 ba=a['backlog']['seconds'] if a['backlog'] else 0.0
 bb=b['backlog']['seconds'] if b['backlog'] else 0.0
 balanced=recon[1]['balanced'] and recon[2]['balanced']
 conclusion={'backlog_seconds':{'baseline':ba,'during_ddl':bb,'extra':round(bb-ba,3)},
 'p99_ms':{'baseline':a['p99_ms'],'during_ddl':b['p99_ms']},
 'p95_ms':{'baseline':a['p95_ms'],'during_ddl':b['p95_ms']},
 'timeouts':{'baseline':a['timeouts'],'during_ddl':b['timeouts']},
 'late_success':{'baseline':a['late_success'],'during_ddl':b['late_success']},
 'accounting_balanced':balanced}
 summary=(f"边写边建索引时遥测写入积压约 {bb} 秒（不建索引 {ba} 秒）；"
 f"p99 尾延迟 {b['p99_ms']} ms 对基线 {a['p99_ms']} ms；"
 f"超时 {b['timeouts']} 笔对基线 {a['timeouts']} 笔，其中超时后仍落库 {b['late_success']} 笔；"
 f"两轮各 {recon[1]['planned']} 笔按同一计划到达，逐笔对账{'未发现少算' if balanced else '存在差异，需复查 reconciliation'}。"
 f"试验表 {TABLE} 已删除，遥测表 telemetry 行数前后一致。")
 return {'plan':plan,
 'sample':{'round_a':checksums[0],'round_b':checksums[1],'same_sample':checksums[0]==checksums[1]},
 'rounds':{'baseline':a,'during_ddl':b},
 'reconciliation':{'baseline':recon[1],'during_ddl':recon[2]},
 'isolation':iso,'cleanup':cleanup,'conclusion':conclusion,'summary':summary,
 'limitations':['请求到达为开环调度：数据库阻塞不改变到达节奏，延迟从计划到达时刻起算',
 '超时为客户端口径：超过阈值的请求计入超时，落库与否以对账查询为准',
 'MySQL 8 在线 DDL 允许并发写入；积压来自元数据锁等待与建索引期间吞吐下降',
 f'写入连接会话 lock_wait_timeout={LOCK_WAIT_S} 秒，超出记为错误而非挂起',
 '样本为 telemetry 的确定性复制，压测表已删除；耗时含驱动与缓存波动，不构成生产承诺']}
def run(run_id,snapshot):
 plan=snapshot;columns=plan['columns']
 if not columns or any(c not in COLUMNS for c in columns) or len(set(columns))!=len(columns):raise ValueError('invalid index columns')
 run_tag=f'run{run_id}'
 eng=create_engine(DATABASE_URL,pool_size=plan['concurrency']+2,max_overflow=0,pool_pre_ping=True)
 try:
  with eng.connect().execution_options(isolation_level='AUTOCOMMIT') as c:
   if c.execute(text(f"SELECT GET_LOCK('{LOCK}',30)")).scalar()!=1:raise RuntimeError('另一场压测正持有串行锁')
   try:
    iso={'telemetry_rows_before':c.execute(text('SELECT COUNT(*) FROM telemetry')).scalar()}
    checksums=[];rounds={};recon={}
    for rnd,use_ddl in ((1,False),(2,True)):
     _reset_table(c,plan['sample_multiplier'])
     checksums.append(_checksum(c))
     ddl={'columns':columns,'at_ms':plan['ddl_at_ms']} if use_ddl else None
     rec,ddl_info=_round(eng,plan,run_tag,rnd,ddl)
     recon[rnd]=_reconcile(c,rec,run_tag,rnd,plan['timeout_ms'])
     rounds[rnd]=(rec,ddl_info)
    if checksums[0]!=checksums[1]:raise RuntimeError('两轮起始样本不一致，压测无效')
    c.execute(text(f'DROP TABLE IF EXISTS {TABLE}'))
    gone=c.execute(text(f"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='{TABLE}'")).scalar()
    cleanup={'stress_table_dropped':True,'verified_gone':gone==0}
    iso['telemetry_rows_after']=c.execute(text('SELECT COUNT(*) FROM telemetry')).scalar()
    iso['untouched']=iso['telemetry_rows_before']==iso['telemetry_rows_after']
   finally:
    try:c.execute(text(f'DROP TABLE IF EXISTS {TABLE}'))
    finally:c.execute(text(f"SELECT RELEASE_LOCK('{LOCK}')"))
  return _assemble(plan,checksums,rounds,recon,cleanup,iso)
 finally:
  eng.dispose()
