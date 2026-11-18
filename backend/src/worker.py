import time,logging,redis
from pathlib import Path
from src.config.settings import REDIS_URL
from src.config.database import Session
from src.models.experiment import Experiment
from src.models.stress import StressRun
from src.services.index_algorithm import run as trial_run
from src.services.stress_runner import run as stress_run
from src.services.audit import log
q=redis.Redis.from_url(REDIS_URL)
def execute(model,kind,run_id,fn):
 with Session() as s:
  row=s.get(model,run_id)
  if not row or row.status!='queued':return
  row.status='running';snapshot=row.snapshot;s.commit()
 try:
  result=fn(run_id,snapshot)
  with Session() as s:r=s.get(model,run_id);r.result=result;r.status='completed';s.commit()
  log('worker',kind+'.completed',str(run_id))
 except Exception as exc:
  logging.exception('task failed')
  with Session() as s:r=s.get(model,run_id);r.status='failed';r.error=str(exc)[:1000];s.commit()
TASKS={'index-trials':(Experiment,'experiment',lambda _id,snap:trial_run(snap)),'stress-runs':(StressRun,'stress',stress_run)}
while True:
 Path('/tmp/worker-heartbeat').touch()
 try:
  item=q.blpop(list(TASKS),timeout=2)
  if not item:continue
  key=item[0].decode() if isinstance(item[0],bytes) else item[0]
  model,kind,fn=TASKS[key]
  execute(model,kind,int(item[1]),fn)
 except Exception:logging.exception('worker loop');time.sleep(2)
