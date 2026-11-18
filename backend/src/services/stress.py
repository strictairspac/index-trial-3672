import redis
from fastapi import HTTPException
from src.config.database import Session
from src.config.settings import REDIS_URL
from src.models.stress import StressRun
from src.utils.serialization import record
queue=redis.Redis.from_url(REDIS_URL)
def list_items():
 with Session() as s:return [record(r) for r in s.query(StressRun).order_by(StressRun.id.desc()).limit(50).all()]
def detail(item_id):
 with Session() as s:
  row=s.get(StressRun,item_id)
  if not row:raise HTTPException(404,'未找到压测')
  return record(row)
def create(data):
 with Session() as s:
  row=StressRun(name=data.name,status='queued',snapshot=data.model_dump())
  s.add(row);s.commit();s.refresh(row);result=record(row)
 try:queue.rpush('stress-runs',result['id'])
 except redis.RedisError:
  with Session() as s:r=s.get(StressRun,result['id']);r.status='failed';r.error='队列不可用，请创建新压测';s.commit()
  raise HTTPException(503,'队列不可用，请稍后重新执行')
 return result
