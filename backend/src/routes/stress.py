import json
from fastapi import APIRouter,Depends
from fastapi.responses import Response
from src.middlewares.auth import current,writer
from src.schemas.business import StressInput
from src.services import stress
from src.controllers.business import start_stress
router=APIRouter()
@router.get('/stress')
def listing(u=Depends(current)):return stress.list_items()
@router.post('/stress')
def create(data:StressInput,u=Depends(writer)):return start_stress(data,u)
@router.get('/stress/{item_id}')
def detail(item_id:int,u=Depends(current)):return stress.detail(item_id)
@router.get('/stress/{item_id}/export')
def export(item_id:int,u=Depends(current)):
 return Response(json.dumps(stress.detail(item_id),ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="stress-{item_id}.json"'})
