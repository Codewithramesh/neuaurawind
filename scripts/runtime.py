"""Shared native Windows/macOS launcher primitives. No shell command interpolation."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.request import ProxyHandler, build_opener

import psutil

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backend.app.config import Settings
from backend.app.storage import private_directory


def venv_python(root=ROOT, windows=None):
    windows = os.name == 'nt' if windows is None else windows
    return root / '.venv' / ('Scripts/python.exe' if windows else 'bin/python')


def detached_options(windows=None):
    windows = os.name == 'nt' if windows is None else windows
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if windows else {'start_new_session': True}


def get_json(url, timeout=3):
    try:
        # Loopback traffic must not go to a corporate/system HTTP proxy.
        with build_opener(ProxyHandler({})).open(url, timeout=timeout) as response:
            return json.load(response)
    except (OSError, ValueError):
        return None


def identity(pid):
    process = psutil.Process(pid)
    return {'pid': pid, 'created': process.create_time(), 'root': str(ROOT)}


def owned_process(state, script=None):
    """Never stop a reused PID, another checkout, or an unrelated service."""
    if state.get('root') != str(ROOT) or not isinstance(state.get('pid'), int):
        return None
    try:
        process = psutil.Process(state['pid'])
        if process.create_time() != state.get('created') or not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
            return None
        command = process.cmdline()
        if script and str(ROOT / 'scripts' / script) not in command:
            return None
        if not script and not (len(command) >= 2 and Path(command[0]).name.lower() in {'ollama', 'ollama.exe'} and command[1] == 'serve'):
            return None
        return process
    except (psutil.Error, OSError):
        return None


def read_state(path):
    try:
        state = json.loads(path.read_text(encoding='utf-8'))
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def wait_stopped(process, timeout):
    deadline = time.monotonic() + timeout
    while True:
        try:
            if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
                return
        except psutil.NoSuchProcess:
            return
        if time.monotonic() >= deadline:
            raise psutil.TimeoutExpired(timeout, pid=process.pid)
        time.sleep(.1)


def write_state(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value), encoding='utf-8')
    # A Windows reader or antivirus scanner can briefly deny replacement.
    for attempt in range(20):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(.05)


def launch(command, log_file, env=None):
    with log_file.open('ab') as log:
        return subprocess.Popen(command, cwd=ROOT, env={**(env or os.environ), 'PYTHONUTF8': '1'}, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT, **detached_options())


def wait_for(url, process, seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('Service exited. See the logs folder inside your configured data folder.')
        if get_json(url, 1) is not None:
            return
        time.sleep(.25)
    raise RuntimeError('Service did not become ready. See the logs folder inside your configured data folder.')


def npm_command(*args):
    # Execute npm's JS entry point directly: npm.cmd needs cmd.exe quoting on Windows.
    node = shutil.which('node')
    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
    if not node or not npm:
        raise RuntimeError('Install Node.js 22.12+ and reopen your terminal.')
    npm_path = Path(npm).resolve()
    candidates = [npm_path.parent / 'node_modules/npm/bin/npm-cli.js', npm_path.parent / 'npm-cli.js',
                  npm_path.parent.parent / 'lib/node_modules/npm/bin/npm-cli.js']
    cli = next((path for path in candidates if path.is_file()), None)
    if not cli:
        raise RuntimeError('Cannot locate npm-cli.js. Use the official Node.js installer and reopen your terminal.')
    return [node, str(cli), *args]
