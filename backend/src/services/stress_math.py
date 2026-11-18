"""Pure statistics for the write stress test. No I/O, no third-party imports.

Every request record carries: sched (planned arrival, seconds from round start),
dispatched/dequeued/finished (actual monotonic offsets) and outcome. Latency is
always measured from the planned arrival time, never from dequeue time."""
def offsets(count,interval_ms):
 return [i*interval_ms/1000.0 for i in range(count)]
def percentile(sorted_vals,p):
 if not sorted_vals:return None
 k=(len(sorted_vals)-1)*p/100.0
 f=int(k);c=min(f+1,len(sorted_vals)-1)
 return round(sorted_vals[f]+(sorted_vals[c]-sorted_vals[f])*(k-f),2)
def latency_ms(r):return (r['finished']-r['sched'])*1000.0
def backlog_window(timed):
 if not timed:return None
 start=min(r['sched'] for r in timed);end=max(r['finished'] for r in timed)
 return {'start_ms':round(start*1000.0,1),'end_ms':round(end*1000.0,1),'seconds':round(end-start,3)}
def max_queue_depth(rec):
 ev=[]
 for r in rec:
  if 'dispatched' in r:ev.append((r['dispatched'],1))
  if 'dequeued' in r:ev.append((r['dequeued'],-1))
 ev.sort(key=lambda e:(e[0],e[1]))
 depth=0;peak=0
 for _,kind in ev:
  depth+=kind
  if depth>peak:peak=depth
 return peak
def timeline(rec,timeout_ms,buckets=40):
 if not rec:return []
 end=0.0
 for r in rec:end=max(end,r['sched'],r.get('finished') or 0.0)
 if end<=0:return []
 width=end/buckets
 rows=[[i*width,0,0,0.0] for i in range(buckets)]
 for r in rec:
  b=min(int(r['sched']/width),buckets-1)
  rows[b][1]+=1
  if 'finished' in r:
   lat=latency_ms(r)
   if lat>rows[b][3]:rows[b][3]=lat
   if lat>timeout_ms:rows[b][2]+=1
 return [[round(t*1000.0),arrived,to,round(m,1)] for t,arrived,to,m in rows if arrived or to]
def round_stats(rec,timeout_ms,buckets=40):
 done=[r for r in rec if 'finished' in r]
 lat=sorted(latency_ms(r) for r in done)
 waits=sorted((r['dequeued']-r['sched'])*1000.0 for r in rec if 'dequeued' in r)
 timed=[r for r in done if latency_ms(r)>timeout_ms]
 return {'planned':len(rec),'finished':len(done),
 'p50_ms':percentile(lat,50),'p95_ms':percentile(lat,95),'p99_ms':percentile(lat,99),
 'max_ms':round(lat[-1],2) if lat else None,'avg_ms':round(sum(lat)/len(lat),2) if lat else None,
 'avg_queue_wait_ms':round(sum(waits)/len(waits),2) if waits else None,
 'max_queue_wait_ms':round(waits[-1],2) if waits else None,
 'timeouts':len(timed),
 'ok':sum(1 for r in done if r.get('outcome')=='ok' and latency_ms(r)<=timeout_ms),
 'late_success':sum(1 for r in done if r.get('outcome')=='ok' and latency_ms(r)>timeout_ms),
 'errors':sum(1 for r in rec if r.get('outcome')=='error'),
 'pending':sum(1 for r in rec if r.get('outcome')=='pending'),
 'max_queue_depth':max_queue_depth(rec),
 'dispatch_max_jitter_ms':round(max((r['dispatched']-r['sched'])*1000.0 for r in rec if 'dispatched' in r),2) if any('dispatched' in r for r in rec) else None,
 'wall_seconds':round(max(r['finished'] for r in done),2) if done else None,
 'backlog':backlog_window(timed),
 'timeline':timeline(rec,timeout_ms,buckets)}
def accounting_balanced(planned,dispatched,accounted,persisted_db,ok,missing,extra):
 """No request may be lost between plan, dispatch, classification and the database."""
 return planned==dispatched==accounted and missing==0 and extra==0 and persisted_db==ok
