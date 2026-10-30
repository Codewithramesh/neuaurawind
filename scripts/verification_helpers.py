"""Synthetic fixture verification ONLY. These actions are not participant identity/consent proof."""
import secrets


def prepare_synthetic(client, source, device_id=None):
    response=client.post('/api/v1/sessions',headers={'Idempotency-Key':secrets.token_hex(16)},json={
        'title':'Synthetic V1 '+source+' verification','source_type':source,'device_id':device_id,
        'purpose':'Validate software with generated speech; no human participants',
        'participant_refs':['SYNTHETIC FIXTURE — no human identity']})
    response.raise_for_status();session=response.json()
    for link in session['participant_links']:
        result=client.post('/api/v1/participant-consent',headers={'X-Consent-Token':link['token']},json={'decision':'grant','informed':True});result.raise_for_status()
    current=client.get('/api/v1/conversations/'+session['conversation_id']).json()
    for action in ['ready','stop']:
        result=client.post('/api/v1/conversations/'+session['conversation_id']+'/transition',json={
            'action':action,'expected_state':current['session_state'],'consent_version':current['consent_version'],'conditions_confirmed':True})
        result.raise_for_status();current=result.json()
    return session


def review_synthetic(client, cid):
    detail=client.get('/api/v1/conversations/'+cid).json()
    for finding in detail['insights']:
        response=client.patch('/api/v1/insights/'+finding['id']+'/review',json={'review_status':'approved','sharing_checked':True});response.raise_for_status()
    response=client.post('/api/v1/conversations/'+cid+'/approve');response.raise_for_status()
