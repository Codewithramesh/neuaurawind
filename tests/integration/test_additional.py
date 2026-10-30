import hashlib
import time
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4
import pytest
from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import inspect,select
from backend.app.config import ROOT
from backend.app.main import create_app
from backend.app.models import Base,Conversation,ProcessingJob
from backend.app.providers import FasterWhisperProvider,ProcessingError
from backend.app.security import RateLimiter


def test_first_run_token_required_and_consumed(settings):
    app=create_app(settings);Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        payload={'name':'First workspace','email':'first@example.test','password':'a-long-password'}
        assert client.post('/api/v1/bootstrap',json=payload).status_code==403
        token=(settings.data_dir/'setup-token').read_text()
        assert client.post('/api/v1/bootstrap',headers={'X-Setup-Token':token},json=payload).status_code==201
        assert not (settings.data_dir/'setup-token').exists()
        assert client.post('/api/v1/bootstrap',headers={'X-Setup-Token':token},json=payload).status_code==409


def test_rate_limiter_reports_retry_after():
    limiter=RateLimiter();limiter.check('actor',limit=2);limiter.check('actor',limit=2)
    with pytest.raises(HTTPException) as exc:limiter.check('actor',limit=2)
    assert exc.value.status_code==429 and exc.value.headers['Retry-After']=='60'


def test_profile_categories_are_extensible_and_validated(client):
    response=client.patch('/api/v1/settings/profile',json={'name':'Retail','industry':'retail','categories':['loyalty_request']})
    assert response.status_code==200 and response.json()['categories']==['loyalty_request']
    assert client.patch('/api/v1/settings/profile',json={'name':'Retail','industry':'retail','categories':['Invalid category']} ).status_code==422
    response=client.get('/api/v1/settings')
    assert response.status_code==200 and isinstance(response.json()['extraction']['ready'], bool)


def test_restart_requeues_interrupted_work(client,app,submit,wav_bytes):
    cid=submit(wav_bytes())['conversation_id']
    with app.state.factory() as db:
        job=db.scalar(select(ProcessingJob));job.status='processing';db.get(Conversation,cid).status='processing';db.commit()
    app.state.pipeline.start()
    try:
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            result=client.get('/api/v1/conversations/'+cid).json()
            if result['status']=='complete':break
            time.sleep(.05)
        assert result['status']=='complete'
    finally:app.state.pipeline.stop()


def test_missing_model_pipeline_and_retry_limit(client,app,submit,wav_bytes,settings):
    app.state.pipeline.transcriber=FasterWhisperProvider(settings)
    cid=submit(wav_bytes())['conversation_id'];app.state.pipeline.process(cid)
    result=client.get('/api/v1/conversations/'+cid).json()
    assert result['job']['error_code']=='MODEL_MISSING' and result['transcript'] is None
    with app.state.factory() as db:
        db.scalar(select(ProcessingJob)).attempts=5;db.commit()
    response=client.post('/api/v1/conversations/'+cid+'/retry')
    assert response.status_code==409 and response.json()['detail']['code']=='RETRY_LIMIT'


def test_optional_captured_time_is_stored_separately(client):
    response=client.post('/api/v1/sessions',headers={'Idempotency-Key':str(uuid4())},json={
        'title':'Offline capture','consent_attested':True,'purpose':'Authorized import','participant_refs':['TEST participant'],'captured_at':'2026-09-01T12:30:00+05:30'})
    assert response.status_code==201
    detail=client.get('/api/v1/conversations/'+response.json()['conversation_id']).json()
    assert detail['captured_at']=='2026-09-01T07:00:00+00:00'
    assert detail['created_at']!=detail['captured_at']
    assert client.post('/api/v1/sessions',headers={'Idempotency-Key':str(uuid4())},json={
        'title':'Naive time','consent_attested':True,'purpose':'Authorized import','participant_refs':['TEST participant'],'captured_at':'2026-09-01T12:30:00'}).status_code==422


def test_migrations_upgrade_downgrade_and_reupgrade(tmp_path,monkeypatch):
    url=f"sqlite:///{tmp_path/'migrations.sqlite3'}"
    monkeypatch.setenv('NEUAURA_DATABASE_URL',url)
    config=Config(str(ROOT/'backend/alembic.ini'))
    command.upgrade(config,'head')
    from sqlalchemy import create_engine
    engine=create_engine(url)
    assert 'devices' in inspect(engine).get_table_names()
    assert 'captured_at' in {x['name'] for x in inspect(engine).get_columns('conversations')}
    with pytest.raises(RuntimeError,match='consent and review history'):
        command.downgrade(config,'base')
    command.upgrade(config,'head')
    assert 'evidence' in inspect(engine).get_table_names()
    engine.dispose()


def test_aggregate_upload_limit_and_stored_integrity(client,app):
    from tests.integration.test_api import create_session
    session=create_session(client,title='Bounded upload').json()
    data=b'x'*700000;headers={'Content-Type':'audio/wav','X-Chunk-SHA256':hashlib.sha256(data).hexdigest()}
    path='/api/v1/sessions/'+session['id']
    assert client.post(path+'/audio?sequence=0',headers=headers,content=data).status_code==200
    assert client.post(path+'/audio?sequence=1',headers=headers,content=data).status_code==413
    (app.state.settings.data_dir/'uploads'/session['conversation_id']/'chunk-0').write_bytes(b'tampered')
    response=client.post(path+'/complete',json={'total_chunks':1,'sha256':hashlib.sha256(data).hexdigest()})
    assert response.status_code==409 and response.json()['detail']['code']=='CHUNK_DAMAGED'


def test_openapi_has_typed_hardware_contract(app):
    schema=app.openapi();operation=schema['paths']['/api/v1/sessions/{session_id}/complete']['post']
    assert operation['responses']['200']['content']['application/json']['schema']['$ref'].endswith('CompletionResponse')
    assert 'DeviceProvisioned' in schema['components']['schemas']


def test_device_provisioning_requires_admin_role(client,app):
    from backend.app.models import User
    from backend.app.security import password_hash
    with app.state.factory() as db:
        admin=db.scalar(select(User))
        db.add(User(org_id=admin.org_id,email='viewer@example.test',password_hash=password_hash('viewer-password-2026'),role='viewer'));db.commit()
    with TestClient(app) as viewer:
        login=viewer.post('/api/v1/auth/login',json={'email':'viewer@example.test','password':'viewer-password-2026'})
        viewer.headers['X-CSRF-Token']=login.json()['csrf']
        assert viewer.get('/api/v1/conversations').status_code==200
        response=viewer.post('/api/v1/devices/register',json={'name':'Unauthorized','model':'test'})
        assert response.status_code==403 and response.json()['detail']['code']=='ADMIN_REQUIRED'
