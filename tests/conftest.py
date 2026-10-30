"""Providers in this file are deliberate test doubles; never imported by the application."""
import hashlib
import io
import math
import struct
import wave
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import Base, Organization, User
from backend.app.providers import TranscriptionResult
from backend.app.schemas import Extraction
from backend.app.security import password_hash

TEST_TEXT = 'The coffee was excellent. We waited twenty minutes for our order.'


class TestSpeechProvider:
    __test__ = False
    calls = 0
    def transcribe(self, audio, language):
        self.calls += 1
        assert audio.is_file()
        return TranscriptionResult(TEST_TEXT, [{"start":0.0,"end":1.0,"text":TEST_TEXT}], 'en', 'TEST_DOUBLE', 'TEST_ONLY')


class TestExtractionProvider:
    __test__ = False
    def extract(self, transcript, industry, categories):
        return Extraction.model_validate({
            'summary':'A guest praised coffee and reported a twenty minute wait.',
            'topics':['coffee','waiting time'],'entities':[],
            'insights':[{'category':'operational_bottleneck','topic':'waiting time','title':'Guest reported a wait',
                'description':'A guest said their order took twenty minutes.', 'sentiment':'negative','basis':'stated',
                'confidence':0.9,'uncertainty':'One conversation; broader frequency is unknown.',
                'evidence':[{'quote':'We waited twenty minutes for our order.','segment_index':0}]}],
            'actions':[{'insight_index':0,'description':'Investigate order preparation times.','priority':'medium'}]})


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / 'data', database_url=f"sqlite:///{tmp_path / 'data/test.sqlite3'}", llm_base_url='http://127.0.0.1:1', extraction_provider='ollama', allow_cloud=False, whisper_model_path=tmp_path / 'model', worker_enabled=False,
                    max_duration_seconds=5, max_upload_mb=1, _env_file=None)


@pytest.fixture
def speech():
    return TestSpeechProvider()


@pytest.fixture
def app(settings, speech):
    app = create_app(settings, transcriber=speech, extractor=TestExtractionProvider())
    Base.metadata.create_all(app.state.engine)
    return app


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        token = (app.state.settings.data_dir / 'setup-token').read_text()
        response = client.post('/api/v1/bootstrap', headers={'X-Setup-Token':token}, json={
            'name':'Test-only café','industry':'restaurant','email':'admin@example.test','password':'test-password-2026'})
        assert response.status_code == 201, response.text
        response = client.post('/api/v1/auth/login', json={'email':'admin@example.test','password':'test-password-2026'})
        assert response.status_code == 200, response.text
        client.headers['X-CSRF-Token'] = response.json()['csrf']
        yield client


@pytest.fixture
def wav_bytes():
    def build(seconds=1, silent=False):
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as out:
            out.setnchannels(1); out.setsampwidth(2); out.setframerate(16000)
            samples = [0 if silent else int(8000*math.sin(i*2*math.pi*220/16000)) for i in range(int(seconds*16000))]
            out.writeframes(struct.pack('<'+'h'*len(samples), *samples))
        return buffer.getvalue()
    return build


def confirm_and_finalize(client, session):
    """Test-only participant actions. Never imported by application code."""
    for participant in session.get('participant_links', []):
        response = client.post('/api/v1/participant-consent', headers={'X-Consent-Token':participant['token']},
            json={'decision':'grant','informed':True})
        assert response.status_code == 200, response.text
    cid = session['conversation_id']
    current = client.get('/api/v1/conversations/'+cid).json()
    for action in ['ready','stop']:
        response = client.post('/api/v1/conversations/'+cid+'/transition', json={'action':action,
            'expected_state':current['session_state'],'consent_version':current['consent_version'],'conditions_confirmed':True})
        assert response.status_code == 200, response.text
        current=response.json()


def approve_results(client, cid):
    detail=client.get('/api/v1/conversations/'+cid).json()
    for finding in detail['insights']:
        response=client.patch('/api/v1/insights/'+finding['id']+'/review',json={'review_status':'approved','sharing_checked':True})
        assert response.status_code==200,response.text
    response=client.post('/api/v1/conversations/'+cid+'/approve')
    assert response.status_code==200,response.text


@pytest.fixture
def submit(client):
    def ingest(audio, source='browser', auth=None, key=None, title='Authorized test conversation'):
        headers = auth or {}
        device_id=client.get('/api/v1/devices').json()[0]['id'] if source=='device' else None
        response = client.post('/api/v1/sessions', headers={'Idempotency-Key':key or str(uuid4())},
            json={'title':title,'source_type':source,'consent_attested':True,'purpose':'Test fixture business feedback','participant_refs':['TEST participant'],'device_id':device_id,'store_id':client.get('/api/v1/stores').json()[0]['id']})
        assert response.status_code == 201, response.text
        session = response.json()
        confirm_and_finalize(client, session)
        response = client.post(f"/api/v1/sessions/{session['id']}/audio", headers={**headers,
            'Content-Type':'audio/wav','X-Chunk-SHA256':hashlib.sha256(audio).hexdigest()}, content=audio)
        assert response.status_code == 200, response.text
        response = client.post(f"/api/v1/sessions/{session['id']}/complete", headers=headers,
            json={'sha256':hashlib.sha256(audio).hexdigest(),'total_chunks':1})
        assert response.status_code == 200, response.text
        return session
    return ingest
