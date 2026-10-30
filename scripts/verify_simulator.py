"""Real HTTP + real STT simulator verification, isolated from the user's workspace."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import httpx

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from backend.app.config import Settings
verification_settings=Settings()
from verification_helpers import prepare_synthetic
parser=argparse.ArgumentParser()
parser.add_argument('audio',type=Path)
parser.add_argument('--synthetic-fixture',action='store_true',required=True,help='Use only generated speech; test consent actions are not real participant consent')
parser.add_argument('--port',type=int,default=8012)
parser.add_argument('--require-complete',action='store_true',help='Require simulator exit 0 and successful real AI extraction')
args=parser.parse_args()
with tempfile.TemporaryDirectory(prefix='neuaura-simulator-') as tmp:
    folder=Path(tmp)
    env={**os.environ,'NEUAURA_DATA_DIR':str(folder),'NEUAURA_DATABASE_URL':f'sqlite:///{folder / "test.sqlite3"}','NEUAURA_WORKER_ENABLED':'true'}
    subprocess.run([sys.executable,'-m','alembic','-c','backend/alembic.ini','upgrade','head'],cwd=root,env=env,check=True)
    command=[sys.executable,'-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port',str(args.port)]
    process=None
    def start():
        global process
        process=subprocess.Popen(command,cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            if process.poll() is not None:raise RuntimeError('Verification server failed to start')
            try:
                if httpx.get(f'http://127.0.0.1:{args.port}/api/v1/health',timeout=1).status_code==200:return
            except httpx.TransportError:pass
            time.sleep(.2)
        raise RuntimeError('Verification server startup timeout')
    def stop():
        if process and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait()
    try:
        start()
        with httpx.Client(base_url=f'http://127.0.0.1:{args.port}',timeout=20) as client:
            password=secrets.token_urlsafe(24)
            response=client.post('/api/v1/bootstrap',headers={'X-Setup-Token':(folder/'setup-token').read_text()},json={
                'name':'Isolated real simulator verification','email':'simulator@example.test','password':password});response.raise_for_status()
            response=client.post('/api/v1/auth/login',json={'email':'simulator@example.test','password':password});response.raise_for_status()
            client.headers['X-CSRF-Token']=response.json()['csrf']
            response=client.post('/api/v1/devices/register',json={'name':'Genuine audio simulator','model':'HTTP','simulated':True});response.raise_for_status();device=response.json()
            credential=folder/'device-credential';credential.write_text(device['credential']);credential.chmod(0o600)
            session=prepare_synthetic(client,'device',device['id'])
            result=subprocess.run([sys.executable,'device-simulator/submit.py',str(args.audio.resolve()),'--url',f'http://127.0.0.1:{args.port}',
                '--device-id',device['id'],'--credential-file',str(credential),'--chunk-bytes','12000','--session-id',session['id']],cwd=root,capture_output=True,text=True,timeout=240)
            rows=client.get('/api/v1/conversations').json()
            if not rows:raise RuntimeError('Simulator did not persist a conversation: '+result.stderr)
            cid=rows[0]['id'];detail=client.get('/api/v1/conversations/'+cid).json()
            assert detail['source_type']=='device' and detail['transcript'],detail
            stop();start()
            persisted=client.get('/api/v1/conversations/'+cid);persisted.raise_for_status()
            assert persisted.json()['transcript']['text']==detail['transcript']['text']
            response=client.post('/api/v1/devices/'+device['id']+'/revoke');response.raise_for_status()
            rejected=client.get('/api/v1/devices/'+device['id'],headers={'Authorization':'Bearer '+device['credential']})
            assert rejected.status_code==401
            report={'ai_model':verification_settings.llm_model,'ai_context_length':verification_settings.llm_context_length,'real_providers_only':True,'synthetic_fixture_consent_actions':True,'simulator_exit_code':result.returncode,'source':'device','status':detail['status'],
                'job':detail['job'],'transcript':detail['transcript'],'persisted_after_real_process_restart':True,'revoked_credential_http_status':rejected.status_code,
                'simulator_output':result.stdout,'physical_hardware_verified':False}
            if args.require_complete and (result.returncode!=0 or detail['status']!='complete'):
                raise RuntimeError('Real simulator analysis did not complete: '+str(detail.get('job')))
            out=root/'local-data/verification/v1-real-simulator.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2))
            print(json.dumps({k:v for k,v in report.items() if k not in {'transcript','simulator_output','job'}},indent=2))
    finally:
        stop()
