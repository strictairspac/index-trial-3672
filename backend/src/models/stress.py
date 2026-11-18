from sqlalchemy import Column,Integer,String,JSON,DateTime,func
from src.config.database import Base
class StressRun(Base):
 __tablename__='stress_runs'
 id=Column(Integer,primary_key=True)
 name=Column(String(120),unique=True,nullable=False)
 status=Column(String(20),default='queued',nullable=False)
 snapshot=Column(JSON,nullable=False)
 result=Column(JSON,nullable=True)
 error=Column(String(1000),nullable=True)
 created_at=Column(DateTime,server_default=func.now())
