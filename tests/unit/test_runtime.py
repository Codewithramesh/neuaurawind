"""Launcher ownership, Windows-specific branches and real portable subprocess lifecycle."""
from collections import defaultdict
import json
import os
from pathlib import Path, PureWindowsPath
import subprocess
import sys
import threading
import time
from uuid import uuid4

import httpx
import psutil
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import runtime
import desktop
from backend.app.cleanup import delete_uploads, pending_file, retry_deletions
from backend.app.config import Settings


def test_windows_interpreter_path_handles_spaces_and_unicode():
    root = PureWindowsPath('C:/Users/Example Person/Projects/நியூஆரா')
    assert str(runtime.venv_python(root, windows=True)) == str(root / '.venv/Scripts/python.exe')
    assert runtime.venv_python(ROOT, windows=False) == ROOT / '.venv/bin/python'


def test_windows_detachment_uses_native_flags(monkeypatch):
    monkeypatch.setattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000, raising=False)
    assert runtime.detached_options(windows=True) == {'creationflags': 0x08000000}
    assert runtime.detached_options(windows=False) == {'start_new_session': True}


def test_ownership_refuses_other_commands_roots_and_reused_pid(monkeypatch):
    class Process:
        def create_time(self): return 42.5
        def is_running(self): return True
        def status(self): return psutil.STATUS_RUNNING
        def cmdline(self): return [sys.executable, str(ROOT / 'scripts/run_server.py')]
    monkeypatch.setattr(psutil, 'Process', lambda pid: Process())
    state = {'pid': 123, 'created': 42.5, 'root': str(ROOT)}
    assert runtime.owned_process(state, 'run_server.py')
    assert runtime.owned_process({**state, 'created': 42.4}, 'run_server.py') is None
    assert runtime.owned_process({**state, 'root': str(ROOT / 'another-project')}, 'run_server.py') is None
    assert runtime.owned_process(state) is None  # not Ollama
    assert runtime.owned_process(state, 'other.py') is None


def test_sqlite_path_preserves_spaces_unicode_and_reserved_characters(tmp_path):
    from sqlalchemy.engine import make_url
    settings = Settings(data_dir=tmp_path / 'Data with spaces தமிழ் #1', _env_file=None)
    assert make_url(settings.database_url).database == str(settings.data_dir / 'neuaura.sqlite3')


def test_npm_runs_node_entrypoint_without_cmd_shell(tmp_path, monkeypatch):
    folder = tmp_path / 'Node with spaces'
    cli = folder / 'node_modules/npm/bin/npm-cli.js'
    cli.parent.mkdir(parents=True)
    cli.touch()
    node, npm = folder / 'node.exe', folder / 'npm.cmd'
    node.touch(); npm.touch()
    monkeypatch.setattr(runtime.shutil, 'which', lambda name: str(node if name == 'node' else npm))
    assert runtime.npm_command('run', 'build') == [str(node), str(cli), 'run', 'build']


def test_locked_media_deletion_is_durable_and_retries(tmp_path, monkeypatch):
    import backend.app.cleanup as cleanup
    cid = str(uuid4())
    folder = tmp_path / 'uploads' / cid
    folder.mkdir(parents=True)
    (folder / 'original').write_bytes(b'private audio')
    (folder / 'chunk-0').write_bytes(b'private audio')
    actual = cleanup.shutil.rmtree
    def locked(path): raise PermissionError('Windows sharing violation')
    monkeypatch.setattr(cleanup.shutil, 'rmtree', locked)
    assert not delete_uploads(tmp_path, cid)
    assert pending_file(tmp_path, cid).is_file()
    # Recreate the worker/locks to represent a restart, then release the OS handle.
    monkeypatch.setattr(cleanup.shutil, 'rmtree', actual)
    retry_deletions(tmp_path, defaultdict(threading.RLock))
    assert not folder.exists()
    assert not pending_file(tmp_path, cid).exists()
    with pytest.raises(ValueError): delete_uploads(tmp_path, '../outside')


def test_shortcut_installer_refuses_unrelated_folder(tmp_path):
    import install_desktop_shortcuts
    (tmp_path / 'NEUAURA B2B').mkdir()
    sentinel = tmp_path / 'NEUAURA B2B/keep.txt'
    sentinel.write_text('unrelated')
    with pytest.raises(RuntimeError, match='another project'):
        install_desktop_shortcuts.install(tmp_path)
    assert sentinel.read_text() == 'unrelated'


def test_stop_does_not_kill_an_unrelated_process(tmp_path):
    from types import SimpleNamespace
    process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    try:
        runtime.write_state(tmp_path / 'server-process.json', {**runtime.identity(process.pid), 'shutdown_token':'test'})
        desktop.stop(SimpleNamespace(data_dir=tmp_path))
        assert process.poll() is None
    finally:
        process.terminate(); process.wait(timeout=10)


def test_real_server_start_stop_restart_in_private_path(tmp_path):
    import socket
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    data = tmp_path / 'NEUAURA Data தமிழ் with spaces'
    env = {**os.environ, 'NEUAURA_DATA_DIR':str(data), 'NEUAURA_DATABASE_URL':'',
           'NEUAURA_WORKER_ENABLED':'false', 'PYTHONUTF8':'1', 'PYTHONPATH':str(ROOT)}
    python = sys.executable
    url = f'http://127.0.0.1:{port}'
    with (tmp_path / 'server.log').open('w', encoding='utf-8') as log, httpx.Client(trust_env=False, timeout=2) as client:
        token = None
        for attempt in range(2):
            process = subprocess.Popen([python, str(ROOT / 'scripts/run_server.py'), '--port', str(port)], cwd=ROOT, env=env, stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    assert process.poll() is None, (tmp_path / 'server.log').read_text(encoding='utf-8')
                    try:
                        health = client.get(url + '/api/v1/health')
                        if health.status_code == 200: break
                    except httpx.HTTPError: pass
                    time.sleep(.2)
                else: pytest.fail('Server failed to become ready')
                assert health.json()['bootstrap_required']
                assert client.get(url + '/').status_code == 200
                current = (data / 'setup-token').read_text()
                if token: assert token == current  # restart preserves private setup state
                token = current
                if attempt == 0:
                    duplicate = subprocess.run([python, str(ROOT / 'scripts/run_server.py'), '--port', str(port)], cwd=ROOT, env=env, capture_output=True, timeout=40)
                    assert duplicate.returncode != 0
                    assert runtime.read_state(data / 'server-process.json')['pid'] == process.pid
                # Wrong/stale requests must not stop a new server instance.
                runtime.write_state(data / 'server-stop.json', {'shutdown_token':'wrong-instance'})
                time.sleep(.3)
                assert process.poll() is None
                stop = subprocess.run([python, str(ROOT / 'scripts/desktop.py'), 'stop'], cwd=ROOT, env=env, capture_output=True, timeout=60)
                assert stop.returncode == 0, stop.stderr.decode('utf-8')
                assert process.wait(timeout=10) == 0
                assert not (data / 'server-process.json').exists()
            finally:
                if process.poll() is None:
                    process.terminate(); process.wait(timeout=15)


@pytest.mark.skipif(os.name != 'nt', reason='Requires native Windows NTFS ACLs and sharing locks')
def test_native_windows_acl_and_locked_file(tmp_path):
    from backend.app.storage import private_directory
    import install_desktop_shortcuts
    data = tmp_path / "Private Data தமிழ் with spaces and ' apostrophe"
    private_directory(data)
    rights = install_desktop_shortcuts.powershell(r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$acl = Get-Acl -LiteralPath $env:NEUAURA_TEST_DATA
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$rules = @($acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]))
@{protected=$acl.AreAccessRulesProtected; current=$user; sids=@($rules | ForEach-Object {$_.IdentityReference.Value}); inherited=@($rules | Where-Object {$_.IsInherited}).Count} | ConvertTo-Json -Compress
""", NEUAURA_TEST_DATA=str(data))
    acl = json.loads(rights)
    assert acl['protected'] and acl['inherited'] == 0
    assert set(acl['sids']) == {acl['current'], 'S-1-5-18'}
    cid = str(uuid4())
    folder = data / 'uploads' / cid
    folder.mkdir(parents=True)
    audio = folder / 'original'
    audio.write_bytes(b'isolated Windows sharing-lock fixture')
    with audio.open('rb'):
        assert not delete_uploads(data, cid)
        assert pending_file(data, cid).exists()
    retry_deletions(data, defaultdict(threading.RLock))
    assert not folder.exists()


@pytest.mark.skipif(os.name != 'nt', reason='Requires Windows shell COM shortcuts')
def test_native_windows_shortcuts_in_redirected_desktop(tmp_path):
    import install_desktop_shortcuts
    target = tmp_path / "Redirected Desktop தமிழ் with spaces and ' apostrophe"
    install_desktop_shortcuts.install(target)
    folder = target / 'NEUAURA B2B'
    assert (folder / 'Start NEUAURA.lnk').is_file()
    assert (folder / 'Project files.lnk').is_file()
    link = json.loads(install_desktop_shortcuts.powershell(r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$shell = New-Object -ComObject WScript.Shell
$link = $shell.CreateShortcut($env:NEUAURA_TEST_LINK)
@{target=$link.TargetPath; args=$link.Arguments; cwd=$link.WorkingDirectory} | ConvertTo-Json -Compress
""", NEUAURA_TEST_LINK=str(folder / 'Start NEUAURA.lnk')))
    assert Path(link['target']) == ROOT / 'Start NEUAURA.cmd'
    assert link['args'] == ''
    assert Path(link['cwd']) == ROOT


def test_desktop_launcher_detached_start_and_stop(tmp_path):
    import socket
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    data = tmp_path / 'Detached Services தமிழ் with spaces'
    env = {**os.environ, 'NEUAURA_DATA_DIR':str(data), 'NEUAURA_DATABASE_URL':'',
           'NEUAURA_WORKER_ENABLED':'false', 'NEUAURA_EXTRACTION_PROVIDER':'openai_compatible',
           'NEUAURA_LLM_BASE_URL':'http://127.0.0.1:1', 'PYTHONUTF8':'1'}
    command = [sys.executable, str(ROOT / 'scripts/desktop.py')]
    try:
        for attempt in range(2):
            result = subprocess.run([*command, 'start', '--port', str(port), '--no-open'], cwd=ROOT, env=env, capture_output=True, timeout=70)
            assert result.returncode == 0, result.stderr.decode('utf-8')
            state = runtime.read_state(data / 'server-process.json')
            assert runtime.owned_process(state, 'run_server.py')
            if attempt: assert state['pid'] == first_pid
            first_pid = state['pid']
            assert runtime.get_json(f'http://127.0.0.1:{port}/api/v1/health')['bootstrap_required']
    finally:
        stop = subprocess.run([*command, 'stop'], cwd=ROOT, env=env, capture_output=True, timeout=60)
        assert stop.returncode == 0, stop.stderr.decode('utf-8')
    assert not runtime.read_state(data / 'server-process.json')
