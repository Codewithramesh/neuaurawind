"""Audio privacy remains effective when Windows delays physical file deletion."""
from sqlalchemy import select
from backend.app.models import AudioFile
from backend.app.cleanup import pending_file, retry_deletions


def test_no_audio_retention_removes_source_and_upload_folder(client, app, settings, submit, wav_bytes):
    session = submit(wav_bytes())
    cid = session['conversation_id']
    folder = settings.data_dir / 'uploads' / cid
    assert (folder / 'original').is_file()
    assert not list(folder.glob('chunk-*'))
    app.state.pipeline.process(cid)
    detail = client.get('/api/v1/conversations/' + cid).json()
    assert detail['status'] == 'complete' and detail['transcript']
    assert not folder.exists()
    assert not detail['audio_retained']


def test_withdrawal_revokes_playback_even_when_file_is_locked(client, app, settings, submit, wav_bytes, monkeypatch):
    import backend.app.cleanup as cleanup
    settings.retain_audio = True
    session = submit(wav_bytes())
    cid = session['conversation_id']
    assert client.get('/api/v1/conversations/' + cid + '/audio').status_code == 200
    actual = cleanup.shutil.rmtree
    def locked(path): raise PermissionError('Windows file is in use')
    monkeypatch.setattr(cleanup.shutil, 'rmtree', locked)
    response = client.post('/api/v1/conversations/' + cid + '/withdraw-consent')
    assert response.status_code == 200
    assert client.get('/api/v1/conversations/' + cid + '/audio').status_code == 409
    assert pending_file(settings.data_dir, cid).exists()
    with app.state.factory() as db:
        audio = db.scalar(select(AudioFile).where(AudioFile.conversation_id == cid))
        assert audio.original_path is None and audio.normalized_path is None
    monkeypatch.setattr(cleanup.shutil, 'rmtree', actual)
    retry_deletions(settings.data_dir, app.state.pipeline.locks)
    assert not (settings.data_dir / 'uploads' / cid).exists()
