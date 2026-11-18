"""Unit checks for src.services.stress_math (pure logic, no DB/Redis needed).
Run: python3 -I test-artifacts/gb-4102/stress_math_test.py"""
import sys
sys.path.insert(0,'/workspace/backend')
from src.services.stress_math import offsets,percentile,round_stats,backlog_window,max_queue_depth,timeline,accounting_balanced
fails=[]
def check(name,cond):
 print(('PASS' if cond else 'FAIL'),name)
 if not cond:fails.append(name)
# 1. write plan offsets: identical inputs -> identical plan (both rounds share it)
check('offsets deterministic',offsets(5,20)==[0.0,0.02,0.04,0.06,0.08] and offsets(5,20)==offsets(5,20))
# 2. percentiles
vals=sorted(range(1,101))
check('percentile p50',percentile(vals,50)==50.5)
check('percentile p99',percentile(vals,99)==99.01)
check('percentile empty',percentile([],95) is None)
# 3. synthetic round: 100 requests at 50ms; requests 20..59 stall 600ms (index build waits for MDL),
#    the rest finish in 5ms. Timeout threshold 500ms. Latency measured from planned arrival.
rec=[]
for i in range(100):
 r={'seq':i,'tag':f'run1-r2-{i}','sched':i*0.05,'dispatched':i*0.05}
 stall=0.6 if 20<=i<60 else 0.005
 r['dequeued']=r['sched']+(0.55 if 20<=i<60 else 0.001)
 r['finished']=r['sched']+stall
 r['outcome']='ok'
 rec.append(r)
st=round_stats(rec,500)
check('all requests accounted',st['planned']==100 and st['finished']==100)
check('timeouts counted from planned arrival',st['timeouts']==40)
check('late success == timed-out ok writes',st['late_success']==40 and st['ok']==60)
check('backlog window',st['backlog'] and st['backlog']['start_ms']==1000.0 and st['backlog']['seconds']==2.55)
check('queue depth grows while writes stall',st['max_queue_depth']>0)
check('no dispatch jitter in plan',st['dispatch_max_jitter_ms']==0.0)
check('errors/pending zero',st['errors']==0 and st['pending']==0)
# 4. no backlog -> no window
fast=[{'seq':0,'sched':0.0,'dispatched':0.0,'dequeued':0.0,'finished':0.004,'outcome':'ok'}]
check('no backlog window when nothing times out',round_stats(fast,500)['backlog'] is None)
# 5. accounting identity: nothing lost between plan, dispatch, classification and the database
check('balanced accounting',accounting_balanced(100,100,100,100,100,0,0))
check('undercount detected (missing in db)',not accounting_balanced(100,100,100,97,100,3,0))
check('undercount detected (dispatch < planned)',not accounting_balanced(100,99,100,100,100,0,0))
check('extra rows detected',not accounting_balanced(100,100,100,100,100,0,2))
# 6. timeline buckets keep every timed-out request visible
tl=timeline(rec,500,buckets=10)
check('timeline covers all arrivals',sum(row[1] for row in tl)==100)
check('timeline keeps all timeouts',sum(row[2] for row in tl)==40)
# 7. mixed outcomes: error and pending still reconcile by count
mixed=rec+[{'seq':100,'tag':'run1-r2-100','sched':5.0,'dispatched':5.0,'dequeued':5.0,'finished':5.01,'outcome':'error'},
 {'seq':101,'tag':'run1-r2-101','sched':5.05,'dispatched':5.05,'outcome':'pending'}]
st2=round_stats(mixed,500)
check('error+pending counted',st2['errors']==1 and st2['pending']==1 and st2['planned']==102)
print('---')
print('ALL PASS' if not fails else f'{len(fails)} FAILURES: {fails}')
sys.exit(1 if fails else 0)
