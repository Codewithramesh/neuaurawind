"""Run a real local audio -> STT -> configured AI workflow in an isolated temporary database.
No provider doubles. Requires a supplied audio file; never captures the microphone itself.
"""
import argparse
import hashlib
import json
import secrets
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from backend.app.config import Settings,ROOT
from backend.app.main import create_app
from backend.app.models import Base
from verification_helpers import prepare_synthetic, review_synthetic

parser=argparse.ArgumentParser()
parser.add_argument('audio',type=Path)
parser.add_argument('--synthetic-fixture',action='store_true',required=True,help='Required: use generated speech with no human participants; test consent actions are not actual consent proof')
parser.add_argument('--require-complete',action='store_true',help='Fail unless real transcription and real AI extraction both succeed')
parser.add_argument('--industry',choices=['restaurant','retail','hospitality','service'],default='restaurant')
parser.add_argument('--review-task',action='store_true',help='Approve one real suggested task through the authenticated API')
args=parser.parse_args()
audio=args.audio.read_bytes()
test_data=Path(tempfile.mkdtemp(prefix='neuaura-real-'))
settings=Settings(data_dir=test_data,database_url=f'sqlite:///{test_data / "test.sqlite3"}',worker_enabled=False)
settings.allowed_hosts=list(set(settings.allowed_hosts+['testserver']))
# All durable records are isolated; providers are exactly the configured real providers.
app=create_app(settings)
Base.metadata.create_all(app.state.engine)
password=secrets.token_urlsafe(24)
with TestClient(app) as client:
    client.post('/api/v1/bootstrap',headers={'X-Setup-Token':(settings.data_dir/'setup-token').read_text()},json={
        'name':'Real audio verification (synthetic fixture)','industry':args.industry,'email':'verification@example.test','password':password}).raise_for_status()
    response=client.post('/api/v1/auth/login',json={'email':'verification@example.test','password':password});response.raise_for_status()
    client.headers['X-CSRF-Token']=response.json()['csrf']
    outputs=[]
    for source in ['browser','device']:
        headers={}
        if source=='device':
            response=client.post('/api/v1/devices/register',json={'name':'Real audio verification simulator','model':'HTTP prototype','simulated':True});response.raise_for_status()
            device=response.json();headers={'Authorization':'Bearer '+device['credential']}
        session=prepare_synthetic(client,source,device['id'] if source=='device' else None)
        response=client.post('/api/v1/sessions/'+session['id']+'/audio',content=audio,headers={**headers,'Content-Type':'audio/wav','X-Chunk-SHA256':hashlib.sha256(audio).hexdigest()});response.raise_for_status()
        response=client.post('/api/v1/sessions/'+session['id']+'/complete',headers=headers,json={'sha256':hashlib.sha256(audio).hexdigest(),'total_chunks':1});response.raise_for_status()
        app.state.pipeline.process(session['conversation_id'])
        detail=client.get('/api/v1/conversations/'+session['conversation_id']).json()
        reviewed = False
        if args.review_task and detail['status']=='complete' and detail['tasks']:
            review_synthetic(client,session['conversation_id'])
            task=detail['tasks'][0]
            response=client.patch('/api/v1/tasks/'+task['id'],json={'status':'approved'});response.raise_for_status()
            reviewed=response.json()['status']=='approved'
            assert reviewed
            detail=client.get('/api/v1/conversations/'+session['conversation_id']).json()
        outputs.append({'task_approved_through_api':reviewed,'source_type':source,'status':detail['status'],'session_state':detail['session_state'],'transcript':detail['transcript'],'job':detail['job'],'insights':detail['insights'],'tasks':detail['tasks']})
    overview=client.get('/api/v1/overview').json()
report={'ai_model':settings.llm_model,'ai_context_length':settings.llm_context_length,'extraction_provider':settings.extraction_provider,'industry':args.industry,'real_providers_only':True,'synthetic_fixture_consent_actions':True,'fixture':str(args.audio),'physical_microphone_verified':False,
        'records':outputs,'overview':overview,'test_data_dir':str(settings.data_dir)}
output=ROOT/'local-data/verification'/('v1-real-pipeline.json' if args.industry=='restaurant' else 'v1-real-'+args.industry+'-pipeline.json');output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,indent=2))
print(json.dumps({'records':[{'source':x['source_type'],'status':x['status'],'transcript_saved':bool(x['transcript']),'error_code':x['job']['error_code'],'task_approved':x['task_approved_through_api']} for x in outputs],'report':str(output)},indent=2))
if any(not x['transcript'] for x in outputs):raise SystemExit(1)
if args.require_complete and any(x['status']!='complete' for x in outputs):raise SystemExit(2)
