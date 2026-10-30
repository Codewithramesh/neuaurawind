"""Governance integration tests. Speech and extraction are explicitly test doubles from conftest."""
import hashlib
import threading
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from backend.app.models import (Conversation, Insight, ParticipantConsent, ProcessingJob, ReviewEvent, Store, Task, Transcript)
from tests.conftest import approve_results, confirm_and_finalize, TestExtractionProvider


def draft(client, **kw):
    payload={'title':'V1 consent test','source_type':'browser','purpose':'Investigate service experience',
             'participant_refs':['Guest 1','Staff 1'],**kw}
    result=client.post('/api/v1/sessions',headers={'Idempotency-Key':str(uuid4())},json=payload)
    assert result.status_code==201,result.text
    return result.json()


def move(client, session, action, **kw):
    cid=session['conversation_id']; current=client.get('/api/v1/conversations/'+cid).json()
    return client.post('/api/v1/conversations/'+cid+'/transition',json={'action':action,
        'expected_state':current['session_state'],'consent_version':current['consent_version'],**kw})


def grant(client, link):
    return client.post('/api/v1/participant-consent',headers={'X-Consent-Token':link['token']},json={'decision':'grant','informed':True})


def member(client, app, email='staff@example.test', role='staff', store_ids=None):
    if store_ids is None: store_ids=[client.get('/api/v1/stores').json()[0]['id']]
    result=client.post('/api/v1/members',json={'email':email,'password':'member-long-password','role':role,'store_ids':store_ids})
    assert result.status_code==201,result.text
    other=TestClient(app);other.__enter__()
    response=other.post('/api/v1/auth/login',json={'email':email,'password':'member-long-password'})
    assert response.status_code==200
    other.headers['X-CSRF-Token']=response.json()['csrf']
    return other,result.json()


def test_attestation_does_not_authorize_capture(client,wav_bytes):
    session=draft(client,consent_attested=True)
    assert session['session_state']=='awaiting_consent'
    assert move(client,session,'start').status_code==409
    assert move(client,session,'ready',conditions_confirmed=True).json()['detail']['code']=='CONSENT_REQUIRED'
    data=wav_bytes()
    result=client.post('/api/v1/sessions/'+session['id']+'/audio',headers={'Content-Type':'audio/wav','X-Chunk-SHA256':hashlib.sha256(data).hexdigest()},content=data)
    assert result.status_code==409
    grant(client,session['participant_links'][0])
    assert move(client,session,'ready',conditions_confirmed=True).status_code==409
    grant(client,session['participant_links'][1])
    assert move(client,session,'ready').json()['detail']['code']=='CAPTURE_CONDITIONS_REQUIRED'
    assert move(client,session,'ready',conditions_confirmed=True).status_code==200


def test_participant_notice_and_explicit_decision(client):
    session=draft(client);token=session['participant_links'][0]['token'];headers={'X-Consent-Token':token}
    notice=client.get('/api/v1/participant-consent',headers=headers).json()
    assert notice['purpose']=='Investigate service experience'
    assert 'identity' in notice['notice'] and 'retention' in notice
    assert client.post('/api/v1/participant-consent',headers=headers,json={'decision':'grant','informed':False}).status_code==422
    assert client.get('/api/v1/participant-consent',headers={'X-Consent-Token':'wrong'}).status_code==410
    assert grant(client,session['participant_links'][0]).json()['status']=='granted'
    detail=client.get('/api/v1/conversations/'+session['conversation_id']).json()
    assert 'token_hash' not in str(detail)


def test_state_pause_resume_interrupt_and_conflicts(client):
    session=draft(client)
    for link in session['participant_links']:grant(client,link)
    assert move(client,session,'ready',conditions_confirmed=True).status_code==200
    assert move(client,session,'start').status_code==200
    assert move(client,session,'start').status_code==409
    assert move(client,session,'pause').status_code==200
    assert move(client,session,'resume').status_code==409
    assert move(client,session,'resume',conditions_confirmed=True).status_code==200
    assert move(client,session,'interrupt').json()['session_state']=='interrupted'
    assert move(client,session,'resume',conditions_confirmed=True).status_code==409
    assert move(client,session,'ready',conditions_confirmed=True).status_code==200
    current=client.get('/api/v1/conversations/'+session['conversation_id']).json()
    assert client.post('/api/v1/conversations/'+session['conversation_id']+'/transition',json={'action':'start','expected_state':'awaiting_consent','consent_version':current['consent_version']}).status_code==409
    assert move(client,session,'stop').json()['session_state']=='finalizing'
    assert move(client,session,'start').status_code==409


def test_duplicate_capture_prevented_and_cancelled_session_closed(client):
    first=draft(client);second=draft(client)
    for session in [first,second]:
        for link in session['participant_links']:grant(client,link)
        move(client,session,'ready',conditions_confirmed=True)
    assert move(client,first,'start').status_code==200
    assert move(client,second,'start').json()['detail']['code']=='CAPTURE_ALREADY_ACTIVE'
    assert move(client,first,'cancel').status_code==200
    assert move(client,first,'ready',conditions_confirmed=True).status_code==409
    assert move(client,second,'start').status_code==200


def test_participant_withdrawal_stops_session_and_invalidates_resume(client):
    session=draft(client)
    for link in session['participant_links']:grant(client,link)
    move(client,session,'ready',conditions_confirmed=True);move(client,session,'start')
    result=client.post('/api/v1/participant-consent',headers={'X-Consent-Token':session['participant_links'][0]['token']},json={'decision':'withdraw','informed':True})
    assert result.json()['session_state']=='interrupted'
    assert move(client,session,'ready',conditions_confirmed=True).status_code==409
    assert grant(client,session['participant_links'][0]).status_code==409
    fresh=client.post('/api/v1/conversations/'+session['conversation_id']+'/participants',json={'participant_refs':['Guest 1','Staff 1']}).json()
    assert fresh['consent_version']==2
    for link in fresh['participant_links']:grant(client,link)
    assert move(client,session,'ready',conditions_confirmed=True).status_code==200


def test_unreviewed_results_are_private_and_unexportable(client,app,submit,wav_bytes):
    cid=submit(wav_bytes())['conversation_id'];app.state.pipeline.process(cid)
    detail=client.get('/api/v1/conversations/'+cid).json()
    assert detail['session_state']=='needs_review'
    assert client.get('/api/v1/insights').json()==[]
    assert client.get('/api/v1/exports').json()['records']==[]
    assert client.patch('/api/v1/tasks/'+detail['tasks'][0]['id'],json={'status':'approved'}).status_code==409
    assert client.post('/api/v1/conversations/'+cid+'/approve').status_code==409
    finding=detail['insights'][0]
    assert client.patch('/api/v1/insights/'+finding['id']+'/review',json={'review_status':'approved'}).status_code==409
    assert client.patch('/api/v1/insights/'+finding['id']+'/review',json={'review_status':'corrected','description':'Review corrected the finding.','recommendation':'Measure order times over a full week.','success_metric':'Median order-to-serve time by shift'}).status_code==200
    approve_results(client,cid)
    assert client.get('/api/v1/insights').json()[0]['review_status']=='approved'
    assert len(client.get('/api/v1/exports').json()['records'])==1
    assert len(client.get('/api/v1/conversations/'+cid).json()['review_history'])>=3


def test_staff_cannot_read_colleagues_raw_data_or_approve(client,app,submit,wav_bytes):
    cid=submit(wav_bytes())['conversation_id'];app.state.pipeline.process(cid)
    detail=client.get('/api/v1/conversations/'+cid).json();approve_results(client,cid)
    staff,account=member(client,app)
    try:
        assert staff.get('/api/v1/conversations/'+cid).status_code==404
        assert staff.get('/api/v1/conversations/'+cid+'/audio').status_code==404
        assert staff.get('/api/v1/conversations').json()==[]
        assert len(staff.get('/api/v1/insights').json())==1
        assert staff.get('/api/v1/exports').status_code==403
        assert staff.get('/api/v1/audit').status_code==403
        assert staff.patch('/api/v1/insights/'+detail['insights'][0]['id']+'/review',json={'review_status':'approved','sharing_checked':True}).status_code==403
        assert staff.post('/api/v1/members',json={'email':'escalate@example.test','password':'member-long-password','role':'admin'}).status_code==403
        assert staff.patch('/api/v1/settings/profile',json={'name':'Oops','industry':'restaurant','categories':[]}).status_code==403
    finally:staff.__exit__(None,None,None)


def test_store_permission_enforced_for_raw_shared_tasks_and_devices(client,app,submit,wav_bytes):
    original=client.get('/api/v1/stores').json()[0]['id']
    other=client.post('/api/v1/stores',json={'name':'Store B'}).json()['id']
    cid=submit(wav_bytes())['conversation_id'];app.state.pipeline.process(cid);approve_results(client,cid)
    device=client.post('/api/v1/devices/register',json={'name':'Store A sim','model':'test','simulated':True,'store_id':original}).json()
    manager,_=member(client,app,email='manager@example.test',role='manager',store_ids=[other])
    try:
        assert manager.get('/api/v1/conversations/'+cid).status_code==404
        assert manager.get('/api/v1/insights').json()==[]
        assert manager.get('/api/v1/tasks').json()==[]
        assert manager.get('/api/v1/devices/'+device['id']).status_code==404
        assert manager.get('/api/v1/overview',headers={'X-Store-Id':original}).status_code==404
        assert manager.get('/api/v1/exports').json()['records']==[]
        assert manager.get('/api/v1/overview').json()['total_conversations']==0
    finally:manager.__exit__(None,None,None)


def test_assignment_validation_and_staff_completion(client,app,submit,wav_bytes):
    cid=submit(wav_bytes())['conversation_id'];app.state.pipeline.process(cid);approve_results(client,cid)
    task=client.get('/api/v1/conversations/'+cid).json()['tasks'][0]
    staff,account=member(client,app)
    other_store=client.post('/api/v1/stores',json={'name':'Other'}).json()['id']
    other,outsider=member(client,app,email='otherstaff@example.test',store_ids=[other_store])
    try:
        path='/api/v1/tasks/'+task['id']
        assert client.patch(path,json={'owner_id':outsider['id']}).status_code==422
        assert client.patch(path,json={'owner_id':account['id'],'status':'approved','due_date':'2026-12-01'}).json()['deadline_basis']=='operator_set'
        assert staff.patch(path,json={'status':'approved'}).status_code==403
        assert staff.patch(path,json={'description':'Privilege change'}).status_code==403
        assert staff.patch(path,json={'status':'completed'}).status_code==200
        assert other.patch(path,json={'status':'completed'}).status_code==404
    finally:staff.__exit__(None,None,None);other.__exit__(None,None,None)


def test_withdrawal_removes_shared_results_and_exports(client,app,submit,wav_bytes,settings):
    settings.retain_audio=True
    cid=submit(wav_bytes())['conversation_id'];app.state.pipeline.process(cid);approve_results(client,cid)
    assert client.get('/api/v1/exports').json()['records']
    response=client.post('/api/v1/conversations/'+cid+'/withdraw-consent')
    assert response.status_code==200
    detail=client.get('/api/v1/conversations/'+cid).json()
    assert detail['transcript'] is None and detail['insights']==[] and not detail['audio_retained']
    assert client.get('/api/v1/insights').json()==[]
    assert client.get('/api/v1/exports').json()['records']==[]
    assert not (settings.data_dir/'uploads'/cid).exists()
    assert client.post('/api/v1/conversations/'+cid+'/retry').status_code==409


@pytest.mark.parametrize('operation',['withdraw-consent','delete'])
def test_model_work_cannot_recreate_withdrawn_or_deleted_records(client,app,submit,wav_bytes,operation):
    entered,released=threading.Event(),threading.Event()
    class Blocking:
        def extract(self,*args):
            entered.set();assert released.wait(5)
            return TestExtractionProvider().extract(*args)
    app.state.pipeline.extractor=Blocking()
    cid=submit(wav_bytes())['conversation_id']
    worker=threading.Thread(target=app.state.pipeline.process,args=(cid,));worker.start()
    try:
        assert entered.wait(5)
        result=client.delete('/api/v1/conversations/'+cid) if operation=='delete' else client.post('/api/v1/conversations/'+cid+'/withdraw-consent')
        assert result.status_code in {200,204}
    finally:released.set();worker.join(5)
    assert not worker.is_alive()
    with app.state.factory() as db:
        assert db.scalar(select(func.count()).select_from(Insight))==0
        assert db.scalar(select(func.count()).select_from(Task))==0
        if operation=='delete': assert db.get(Conversation,cid) is None
        else: assert db.scalar(select(ProcessingJob)).status=='cancelled'


def test_corrected_transcript_invalidates_quotes_and_timestamps(client,app,submit,wav_bytes):
    cid=submit(wav_bytes())['conversation_id'];app.state.pipeline.process(cid);approve_results(client,cid)
    finding=client.get('/api/v1/conversations/'+cid).json()['insights'][0]
    result=client.patch('/api/v1/conversations/'+cid+'/transcript',json={'text':'The actual corrected transcript contains different words.','summary':'Corrected by manager.'})
    assert result.status_code==200
    assert result.json()['transcript']['provider']=='human_corrected'
    assert result.json()['insights'][0]['evidence_status']=='invalid_after_correction'
    assert result.json()['insights'][0]['evidence'][0]['start'] is None
    assert client.get('/api/v1/insights').json()==[]
    assert client.patch('/api/v1/insights/'+finding['id']+'/review',json={'review_status':'approved','sharing_checked':True}).status_code==409


def test_retention_expiration_of_source_restricts_derived_records(client,app,submit,wav_bytes,settings):
    cid=submit(wav_bytes())['conversation_id'];app.state.pipeline.process(cid);approve_results(client,cid)
    policy={'raw_audio_hours':1,'transcript_days':1,'derived_days':3,'consent_days':5}
    assert client.patch('/api/v1/settings/retention',json=policy).status_code==200
    with app.state.factory() as db:
        db.get(Conversation,cid).created_at=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat();db.commit()
    app.state.pipeline.retention()
    with app.state.factory() as db:
        assert db.get(Transcript,cid) is None
        finding=db.scalar(select(Insight));assert finding.review_status=='restricted' and finding.evidence_status=='source_expired'
    assert client.get('/api/v1/exports').json()['records']==[]


def test_device_cannot_prepare_consent_or_control_unintegrated_hardware(client):
    physical=client.post('/api/v1/devices/register',json={'name':'Unverified wearable','model':'Unknown'}).json()
    assert physical['battery'] is None and physical['capabilities']['recording_indicator'] is False
    assert client.post('/api/v1/sessions',headers={'Authorization':'Bearer '+physical['credential'],'Idempotency-Key':str(uuid4())},json={'title':'Bad','source_type':'device','purpose':'Not operator prepared','participant_refs':['Guest 1']}).status_code==403
    session=draft(client,source_type='device',device_id=physical['id'])
    for link in session['participant_links']:grant(client,link)
    move(client,session,'ready',conditions_confirmed=True)
    assert move(client,session,'start').status_code==501


def test_csv_export_neutralizes_spreadsheet_formulas(client,app,submit,wav_bytes):
    cid=submit(wav_bytes())['conversation_id'];app.state.pipeline.process(cid)
    finding=client.get('/api/v1/conversations/'+cid).json()['insights'][0]
    client.patch('/api/v1/insights/'+finding['id']+'/review',json={'review_status':'corrected','description':'=HYPERLINK("https://example.test")'})
    approve_results(client,cid)
    response=client.get('/api/v1/exports?format=csv')
    assert response.status_code==200 and "'=HYPERLINK" in response.text


def test_membership_changes_invalidate_sessions_and_do_not_escalate(client,app):
    staff,account=member(client,app)
    try:
        assert client.patch('/api/v1/members/'+account['id'],json={'role':'staff','store_ids':account['store_ids'],'active':False}).status_code==200
        assert staff.get('/api/v1/auth/me').status_code==401
        me=client.get('/api/v1/auth/me').json()['user']
        assert client.patch('/api/v1/members/'+me['id'],json={'role':'staff','store_ids':[]}).status_code==409
    finally:staff.__exit__(None,None,None)


def test_staff_capture_and_store_manager_review(client,app,wav_bytes):
    staff,_=member(client,app)
    manager,_=member(client,app,email='reviewer@example.test',role='manager')
    try:
        session=draft(staff);confirm_and_finalize(staff,session)
        audio=wav_bytes();headers={'Content-Type':'audio/wav','X-Chunk-SHA256':hashlib.sha256(audio).hexdigest()}
        assert staff.post('/api/v1/sessions/'+session['id']+'/audio',headers=headers,content=audio).status_code==200
        assert staff.post('/api/v1/sessions/'+session['id']+'/complete',json={'sha256':hashlib.sha256(audio).hexdigest(),'total_chunks':1}).status_code==200
        cid=session['conversation_id'];app.state.pipeline.process(cid)
        assert staff.get('/api/v1/conversations/'+cid).json()['transcript']
        assert staff.post('/api/v1/conversations/'+cid+'/approve').status_code==403
        approve_results(manager,cid)
        assert len(staff.get('/api/v1/insights').json())==1
    finally:staff.__exit__(None,None,None);manager.__exit__(None,None,None)


def test_reanalysis_uses_corrected_transcript_without_speech_or_old_findings(client,app,submit,wav_bytes,speech):
    cid=submit(wav_bytes())['conversation_id'];app.state.pipeline.process(cid);approve_results(client,cid)
    text='A corrected customer statement about a service delay.'
    client.patch('/api/v1/conversations/'+cid+'/transcript',json={'text':text})
    class CorrectedExtractor:
        def extract(self,transcript,*args):
            assert transcript.text==text
            result=TestExtractionProvider().extract(transcript,*args)
            result.insights[0].evidence[0].quote=text
            result.insights[0].evidence[0].segment_index=None
            return result
    app.state.pipeline.extractor=CorrectedExtractor()
    assert client.post('/api/v1/conversations/'+cid+'/reanalyze').status_code==200
    assert client.post('/api/v1/conversations/'+cid+'/reanalyze').status_code==409
    app.state.pipeline.process(cid)
    detail=client.get('/api/v1/conversations/'+cid).json()
    assert detail['status']=='complete' and speech.calls==1
    assert len(detail['insights'])==1 and detail['insights'][0]['evidence'][0]['quote']==text
    assert detail['insights'][0]['review_status']=='unreviewed'
    assert len(detail['tasks'])==1 and detail['tasks'][0]['status']=='suggested'
    assert client.get('/api/v1/exports').json()['records']==[]


def test_device_provider_contracts_do_not_invent_telemetry():
    from backend.app.device_provider import SimulatedDeviceProvider, TransferOnlyProvider
    simulator=SimulatedDeviceProvider()
    assert simulator.capabilities.remote_controls and not simulator.capabilities.recording_indicator
    assert not simulator.capabilities.battery_reporting
    assert simulator.validate_command('pause') is None
    with pytest.raises(ValueError):simulator.validate_command('unsupported')
    with pytest.raises(NotImplementedError):TransferOnlyProvider().validate_command('start')


def test_dashboard_and_history_filters_preserve_review_and_store_scopes(client,app,submit,wav_bytes):
    cid=submit(wav_bytes())['conversation_id'];app.state.pipeline.process(cid)
    assert client.get('/api/v1/conversations?status=needs_review').json()[0]['id']==cid
    assert client.get('/api/v1/conversations?status=approved').json()==[]
    approve_results(client,cid)
    assert client.get('/api/v1/conversations?status=approved').json()[0]['id']==cid
    assert client.get('/api/v1/overview?date_to=2000-01-01').json()['negative']==0
    assert client.get('/api/v1/overview?date_from=2000-01-01').json()['negative']==1
    assert client.get('/api/v1/overview?date_from=invalid').status_code==422


def test_missing_capture_heartbeat_expires_session_and_prevents_silent_resume(client,app):
    session=draft(client)
    for link in session['participant_links']:grant(client,link)
    move(client,session,'ready',conditions_confirmed=True);move(client,session,'start')
    path='/api/v1/conversations/'+session['conversation_id']
    assert client.post(path+'/capture-heartbeat',json={'state':'recording','consent_version':1}).json()['lease_seconds']==20
    assert client.post(path+'/capture-heartbeat',json={'state':'paused','consent_version':1}).status_code==409
    with app.state.factory() as db:
        db.get(Conversation,session['conversation_id']).state_updated_at=(datetime.now(timezone.utc)-timedelta(seconds=30)).isoformat();db.commit()
    app.state.pipeline.expire_captures()
    assert client.get(path).json()['session_state']=='interrupted'
    assert move(client,session,'resume',conditions_confirmed=True).status_code==409
    assert move(client,session,'ready',conditions_confirmed=True).status_code==200


def test_task_deadline_claim_requires_transcript_evidence_and_human_review(client,app,submit,wav_bytes):
    cid=submit(wav_bytes())['conversation_id'];app.state.pipeline.process(cid);approve_results(client,cid)
    task=client.get('/api/v1/conversations/'+cid).json()['tasks'][0]
    path='/api/v1/tasks/'+task['id']
    assert client.patch(path,json={'due_date':'2026-12-01','deadline_basis':'reviewer_confirmed_commitment','deadline_quote':'Invented commitment'}).status_code==422
    assert client.patch(path,json={'due_date':'2026-12-01'}).json()['deadline_basis']=='operator_set'
    # A reviewer corrects the test transcript to include an actual dated commitment.
    original=client.get('/api/v1/conversations/'+cid).json()['transcript']['text']
    quote='I will call you on December 1, 2026.'
    client.patch('/api/v1/conversations/'+cid+'/transcript',json={'text':original+' '+quote})
    approve_results(client,cid)
    response=client.patch(path,json={'due_date':'2026-12-01','deadline_basis':'reviewer_confirmed_commitment','deadline_quote':quote})
    assert response.status_code==200 and response.json()['deadline_basis']=='reviewer_confirmed_commitment'
    assert client.patch(path,json={'owner':'Invented member'}).status_code==422


def test_capture_watchdog_is_independent_of_a_blocked_ai_job(client,app,submit,wav_bytes):
    import time
    entered,released=threading.Event(),threading.Event()
    class Blocking:
        def extract(self,*args):
            entered.set();assert released.wait(10)
            return TestExtractionProvider().extract(*args)
    app.state.pipeline.extractor=Blocking()
    submit(wav_bytes())
    app.state.pipeline.start()
    try:
        assert entered.wait(5)
        session=draft(client)
        for link in session['participant_links']:grant(client,link)
        move(client,session,'ready',conditions_confirmed=True);move(client,session,'start')
        with app.state.factory() as db:
            db.get(Conversation,session['conversation_id']).state_updated_at=(datetime.now(timezone.utc)-timedelta(seconds=30)).isoformat();db.commit()
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if client.get('/api/v1/conversations/'+session['conversation_id']).json()['session_state']=='interrupted':break
            time.sleep(.05)
        else:pytest.fail('Capture watchdog was blocked by AI work')
    finally:released.set();app.state.pipeline.stop()


def test_retention_expiry_prevents_inflight_ai_from_recreating_derived_records(client,app,submit,wav_bytes):
    entered,released=threading.Event(),threading.Event()
    class Blocking:
        def extract(self,*args):
            entered.set();assert released.wait(5)
            return TestExtractionProvider().extract(*args)
    app.state.pipeline.extractor=Blocking()
    cid=submit(wav_bytes())['conversation_id']
    worker=threading.Thread(target=app.state.pipeline.process,args=(cid,));worker.start()
    try:
        assert entered.wait(5)
        client.patch('/api/v1/settings/retention',json={'raw_audio_hours':1,'transcript_days':1,'derived_days':3,'consent_days':5})
        with app.state.factory() as db:
            db.get(Conversation,cid).created_at=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat();db.commit()
        app.state.pipeline.retention()
    finally:released.set();worker.join(5)
    with app.state.factory() as db:
        assert db.get(Transcript,cid) is None
        assert db.scalar(select(func.count()).select_from(Insight))==0
        assert db.scalar(select(ProcessingJob)).error_code=='RETENTION_EXPIRED'
