import hashlib
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func,select
from backend.app.main import create_app
from backend.app.models import (AudioFile,AuthSession,Consent,Conversation,Device,Evidence,Insight,Organization,
                                ProcessingJob,Task,Transcript,UploadSession,User,ParticipantConsent,ReviewEvent)
from backend.app.providers import ProcessingError
from backend.app.security import password_hash
from tests.conftest import TestExtractionProvider, confirm_and_finalize, approve_results


def create_session(client,headers=None,**overrides):
    response=client.post('/api/v1/sessions',headers={'Idempotency-Key':str(uuid4()),**(headers or {})},
        json={'title':'Test capture','source_type':'browser','consent_attested':True,
              'purpose':'Test fixture feedback','participant_refs':['TEST participant'],**overrides})
    if response.status_code==201: confirm_and_finalize(client,response.json())
    return response


def chunk(client,sid,data,sequence=0,headers=None,mime='audio/wav',checksum=None):
    return client.post(f'/api/v1/sessions/{sid}/audio?sequence={sequence}',content=data,
        headers={'Content-Type':mime,'X-Chunk-SHA256':checksum or hashlib.sha256(data).hexdigest(),**(headers or {})})


def finish(client,sid,data,count=1,headers=None):
    return client.post(f'/api/v1/sessions/{sid}/complete',headers=headers or {},json={
        'sha256':hashlib.sha256(data).hexdigest(),'total_chunks':count})


def test_empty_metrics_are_real(client):
    overview=client.get('/api/v1/overview').json()
    assert overview['total_conversations']==overview['positive']==overview['negative']==overview['open_tasks']==0
    assert all(x['conversations']==0 for x in overview['trend'])


def test_authentication_and_csrf(app,client):
    with TestClient(app) as anonymous:
        assert anonymous.get('/api/v1/conversations').status_code==401
        assert anonymous.post('/api/v1/devices/register',json={'name':'bad','model':'bad'}).status_code==401
        assert anonymous.post('/api/v1/auth/login',json={'email':'none@example.test','password':'wrong'}).status_code==401
    original=client.headers.pop('X-CSRF-Token')
    assert create_session(client).status_code==403
    client.headers['X-CSRF-Token']=original
    assert client.post('/api/v1/sessions',headers={'Origin':'https://evil.example.test'},json={}).status_code==403
    assert client.get('/api/v1/health',headers={'Host':'evil.example.test'}).status_code==400


def test_consent_and_source_validation(client):
    assert create_session(client,consent_attested=False).status_code==422
    assert create_session(client,source_type='device').status_code==422
    assert client.post('/api/v1/sessions',json={'title':'Test','consent_attested':True}).status_code==422


def test_idempotent_session_and_conflict(client):
    key=str(uuid4());body={'title':'Same capture','consent_attested':True,'purpose':'Fixture test','participant_refs':['TEST participant']}
    first=client.post('/api/v1/sessions',headers={'Idempotency-Key':key},json=body)
    again=client.post('/api/v1/sessions',headers={'Idempotency-Key':key},json=body)
    assert first.json()['id']==again.json()['id']
    body['title']='Different capture'
    assert client.post('/api/v1/sessions',headers={'Idempotency-Key':key},json=body).status_code==409
    assert client.get('/api/v1/overview').json()['total_conversations']==1


def test_chunk_order_duplicate_missing_and_integrity(client,wav_bytes):
    session=create_session(client).json();sid=session['id'];data=wav_bytes();a,b=data[:1000],data[1000:]
    assert chunk(client,sid,b,sequence=1).status_code==200
    missing=finish(client,sid,data,count=2)
    assert missing.status_code==409 and missing.json()['detail']['code']=='MISSING_CHUNKS'
    assert chunk(client,sid,a).status_code==200
    assert chunk(client,sid,a).json()['duplicate'] is True
    assert chunk(client,sid,b).status_code==409
    assert finish(client,sid,b,count=2).status_code==422
    assert finish(client,sid,data,count=2).status_code==200
    assert finish(client,sid,data,count=2).json()['duplicate'] is True
    assert finish(client,sid,b,count=2).status_code==409
    assert client.get(f'/api/v1/sessions/{sid}/status').json()['received_chunks']==[0,1]


def test_upload_type_empty_checksum_size(client):
    sid=create_session(client).json()['id']
    assert chunk(client,sid,b'bad',mime='text/html').status_code==415
    assert chunk(client,sid,b'').status_code==422
    assert chunk(client,sid,b'bad',checksum='0'*64).status_code==422
    assert chunk(client,sid,b'x'*(1024*1024+1)).status_code==413


def test_cancel_abandoned_upload(client,settings):
    session=create_session(client).json();chunk(client,session['id'],b'data')
    assert client.delete('/api/v1/sessions/'+session['id']).status_code==204
    assert not (settings.data_dir/'uploads'/session['conversation_id']).exists()
    assert client.get('/api/v1/conversations/'+session['conversation_id']).status_code==404


def test_shared_pipeline_evidence_tasks_and_deletion(client,app,wav_bytes,submit,settings):
    session=submit(wav_bytes());cid=session['conversation_id']
    app.state.pipeline.process(cid)
    detail=client.get('/api/v1/conversations/'+cid).json()
    assert detail['status']=='complete'
    assert detail['transcript']['provider']=='TEST_DOUBLE'
    assert detail['insights'][0]['evidence'][0]['start']==0
    assert detail['tasks'][0]['status']=='suggested'
    assert detail['audio_retained'] is False
    assert not (settings.data_dir/'uploads'/cid/'original').exists()
    overview=client.get('/api/v1/overview').json()
    assert (overview['succeeded'],overview['negative'],overview['open_tasks'])==(1,0,0)
    assert overview['awaiting_review']==1
    approve_results(client,cid)
    assert client.get('/api/v1/overview').json()['negative']==1
    task=detail['tasks'][0]
    for status in ['approved','completed','approved','dismissed']:
        response=client.patch('/api/v1/tasks/'+task['id'],json={'status':status,'owner_id':client.get('/api/v1/auth/me').json()['user']['id'],'due_date':'2026-12-01'})
        assert response.status_code==200 and response.json()['status']==status
    assert client.patch('/api/v1/tasks/'+task['id'],json={'status':None}).status_code==422
    assert client.get('/api/v1/conversations?q=coffee').json()[0]['id']==cid
    assert client.get('/api/v1/conversations?q=zzzz').json()==[]
    assert client.delete('/api/v1/conversations/'+cid).status_code==204
    with app.state.factory() as db:
        for model in [Conversation,UploadSession,AudioFile,Transcript,Insight,Evidence,Task,ProcessingJob,Consent,ParticipantConsent,ReviewEvent]:
            assert db.scalar(select(func.count()).select_from(model))==0,model.__name__
    assert client.get('/api/v1/overview').json()['total_conversations']==0


def test_ai_failure_keeps_transcript_and_retry_skips_stt(client,app,wav_bytes,submit,speech):
    class Unavailable:
        def extract(self,*args):raise ProcessingError('AI_UNAVAILABLE','Test provider deliberately unavailable')
    app.state.pipeline.extractor=Unavailable()
    cid=submit(wav_bytes())['conversation_id'];app.state.pipeline.process(cid)
    detail=client.get('/api/v1/conversations/'+cid).json()
    assert detail['status']=='failed' and detail['transcript']
    assert not detail['insights'] and not detail['tasks']
    assert client.post('/api/v1/conversations/'+cid+'/retry').status_code==200
    app.state.pipeline.extractor=TestExtractionProvider();app.state.pipeline.process(cid)
    assert speech.calls==1
    assert client.get('/api/v1/conversations/'+cid).json()['status']=='complete'


def test_corrupt_audio_fails_without_transcript(client,app,submit):
    cid=submit(b'not valid audio')['conversation_id'];app.state.pipeline.process(cid)
    detail=client.get('/api/v1/conversations/'+cid).json()
    assert detail['status']=='failed' and detail['job']['error_code']=='INVALID_AUDIO'
    assert detail['transcript'] is None and detail['summary'] is None
    assert client.post('/api/v1/conversations/'+cid+'/retry').status_code==409


def test_device_credentials_revocation_and_same_pipeline(client,app,wav_bytes,submit):
    device=client.post('/api/v1/devices/register',json={'name':'Test simulator','model':'TEST_ONLY','simulated':True}).json()
    auth={'Authorization':'Bearer '+device['credential']}
    assert 'credential' not in client.get('/api/v1/devices').json()[0]
    beat=client.post(f"/api/v1/devices/{device['id']}/heartbeat",headers=auth,json={'battery':72,'firmware':'test1'})
    assert beat.status_code==200 and beat.json()['simulated'] is True
    cid=submit(wav_bytes(),source='device',auth=auth)['conversation_id'];app.state.pipeline.process(cid)
    detail=client.get('/api/v1/conversations/'+cid).json()
    assert detail['status']=='complete' and detail['device_id']==device['id']
    assert detail['transcript']['provider']=='TEST_DOUBLE'
    assert create_session(client,headers=auth).status_code==403
    assert client.post(f"/api/v1/devices/{device['id']}/revoke").status_code==200
    assert client.get(f"/api/v1/devices/{device['id']}",headers=auth).status_code==401


def test_device_cannot_access_other_device_session(client):
    devices=[client.post('/api/v1/devices/register',json={'name':f'D{i}','model':'test','simulated':True}).json() for i in range(2)]
    auth=[{'Authorization':'Bearer '+d['credential']} for d in devices]
    session=create_session(client,source_type='device',device_id=devices[0]['id']).json()
    assert client.get('/api/v1/sessions/'+session['id']+'/status',headers=auth[1]).status_code==404
    assert client.post(f"/api/v1/devices/{devices[1]['id']}/sessions",headers={**auth[0],'Idempotency-Key':str(uuid4())},json={'title':'Test','source_type':'device','consent_attested':True,'purpose':'Fixture test','participant_refs':['TEST participant']}).status_code==403


def test_organization_isolation(client,app,wav_bytes,submit):
    cid=submit(wav_bytes())['conversation_id'];app.state.pipeline.process(cid)
    detail=client.get('/api/v1/conversations/'+cid).json();task=detail['tasks'][0]['id']
    device=client.post('/api/v1/devices/register',json={'name':'Org1','model':'test'}).json()['id']
    with app.state.factory() as db:
        other=Organization(name='Separate tenant',industry='retail');db.add(other);db.flush()
        db.add(User(org_id=other.id,email='other@example.test',password_hash=password_hash('another-password')));db.commit()
    with TestClient(app) as other_client:
        login=other_client.post('/api/v1/auth/login',json={'email':'other@example.test','password':'another-password'})
        other_client.headers['X-CSRF-Token']=login.json()['csrf']
        assert other_client.get('/api/v1/conversations').json()==[]
        assert other_client.get('/api/v1/insights').json()==[]
        assert other_client.get('/api/v1/tasks').json()==[]
        assert other_client.get('/api/v1/overview').json()['total_conversations']==0
        for path in ['/conversations/'+cid,'/devices/'+device]:assert other_client.get('/api/v1'+path).status_code==404
        assert other_client.delete('/api/v1/conversations/'+cid).status_code==404
        assert other_client.patch('/api/v1/tasks/'+task,json={'status':'approved'}).status_code==404


def test_persistence_survives_new_app(client,app,settings,wav_bytes,submit,speech):
    cid=submit(wav_bytes())['conversation_id'];app.state.pipeline.process(cid)
    new_app=create_app(settings,transcriber=speech,extractor=TestExtractionProvider())
    with TestClient(new_app) as restarted:
        response=restarted.post('/api/v1/auth/login',json={'email':'admin@example.test','password':'test-password-2026'})
        assert response.status_code==200
        assert restarted.get('/api/v1/conversations/'+cid).json()['status']=='complete'
        assert restarted.get('/api/v1/overview').json()['open_tasks']==0
        assert restarted.get('/api/v1/overview').json()['awaiting_review']==1


def test_retention_removes_old_conversation_and_files(client,app,wav_bytes,submit,settings):
    cid=submit(wav_bytes())['conversation_id']
    with app.state.factory() as db:
        db.get(Conversation,cid).created_at=(datetime.now(timezone.utc)-timedelta(days=31)).isoformat();db.commit()
    app.state.pipeline.retention()
    assert client.get('/api/v1/conversations/'+cid).status_code==404
    assert not (settings.data_dir/'uploads'/cid).exists()


def test_retained_audio_authorized_only(client,app,wav_bytes,submit,settings):
    settings.retain_audio=True
    cid=submit(wav_bytes())['conversation_id'];app.state.pipeline.process(cid)
    assert client.get('/api/v1/conversations/'+cid).json()['audio_retained'] is True
    assert client.get('/api/v1/conversations/'+cid+'/audio').content==wav_bytes()
    with TestClient(app) as anonymous:
        assert anonymous.get('/api/v1/conversations/'+cid+'/audio').status_code==401


def test_session_expiry(client,app):
    with app.state.factory() as db:
        session=db.scalar(select(AuthSession));session.expires_at='2000-01-01T00:00:00+00:00';db.commit()
    assert client.get('/api/v1/auth/me').status_code==401
