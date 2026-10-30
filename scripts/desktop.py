"""Native local service controls for Windows and macOS; no automatic downloads."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.parse import urlparse
import webbrowser

from filelock import FileLock
import psutil
from runtime import (ROOT, Settings, get_json, identity, launch, owned_process, private_directory,
                     read_state, venv_python, wait_for, wait_stopped, write_state)


def ollama_binary():
    found = shutil.which('ollama')
    if found:
        return found
    candidates = [Path('/opt/homebrew/bin/ollama'), Path('/usr/local/bin/ollama')]
    if os.name == 'nt' and os.environ.get('LOCALAPPDATA'):
        candidates.insert(0, Path(os.environ['LOCALAPPDATA']) / 'Programs/Ollama/ollama.exe')
    return next((str(p) for p in candidates if p.is_file()), None)


def start(settings, open_browser, port=8000):
    base = settings.llm_base_url.rstrip('/')
    if settings.extraction_provider == 'ollama' and get_json(base + '/api/tags') is None:
        parsed = urlparse(base)
        if parsed.hostname not in {'localhost', '127.0.0.1'} or parsed.scheme != 'http' or parsed.path or parsed.username or parsed.query:
            raise RuntimeError('Start your configured inference server separately. This launcher starts loopback Ollama only.')
        binary = ollama_binary()
        if not binary:
            raise RuntimeError('Install Ollama from https://ollama.com/download and reopen the launcher. See docs/WINDOWS_SETUP.md or docs/LOCAL_SETUP.md.')
        env = {**os.environ, 'OLLAMA_HOST': f'127.0.0.1:{parsed.port or 11434}', 'OLLAMA_NUM_PARALLEL': '1',
               'OLLAMA_MAX_LOADED_MODELS': '1', 'OLLAMA_KEEP_ALIVE': '1m', 'OLLAMA_FLASH_ATTENTION': '1',
               'OLLAMA_KV_CACHE_TYPE': 'q8_0', 'OLLAMA_NO_CLOUD': '1'}
        # Preserve this Mac's existing project-local weights; fresh installations
        # use Ollama's native store, also used by the Windows tray application.
        if (ROOT / 'models/ollama').is_dir() and not env.get('OLLAMA_MODELS'):
            env['OLLAMA_MODELS'] = str(ROOT / 'models/ollama')
        process = launch([binary, 'serve'], settings.data_dir / 'logs/ollama.log', env)
        write_state(settings.data_dir / 'ollama-process.json', identity(process.pid))
        wait_for(base + '/api/tags', process)
    url = f'http://127.0.0.1:{port}/api/v1/health'
    state = read_state(settings.data_dir / 'server-process.json')
    if get_json(url) is None:
        process = launch([str(venv_python()), str(ROOT / 'scripts/run_server.py'), '--port', str(port)],
                         settings.data_dir / 'logs/server.log')
        wait_for(url, process)
    elif not owned_process(state, 'run_server.py') or state.get('port') != port:
        # A legacy Mac server may be running. Reuse without claiming ownership.
        print('A server already answers on this port. Reusing it; this launcher will not claim ownership.')
    print(f'NEUAURA: http://localhost:{port}\nProject: {ROOT}\nData and logs: {settings.data_dir}')
    print('Speech model: ' + str(settings.whisper_model_path))
    if settings.extraction_provider == 'ollama':
        tags = get_json(base + '/api/tags') or {}
        installed = any(m.get('name') == settings.llm_model for m in tags.get('models', []))
        print('AI model: ' + settings.llm_model + (' — installed' if installed else ' — download explicitly: ollama pull ' + settings.llm_model))
    health = get_json(url) or {}
    if health.get('bootstrap_required'):
        print('First use: run the Copy setup token shortcut, paste into the browser, and choose your own email/password.')
    if open_browser:
        webbrowser.open(f'http://localhost:{port}')


def stop(settings):
    state_file = settings.data_dir / 'server-process.json'
    state = read_state(state_file)
    process = owned_process(state, 'run_server.py')
    if process:
        write_state(settings.data_dir / 'server-stop.json', {'shutdown_token': state['shutdown_token']})
        try:
            wait_stopped(process, timeout=30)
        except psutil.TimeoutExpired:
            raise RuntimeError('Graceful shutdown is still pending. Wait for processing to finish and run Stop again.')
        print('NEUAURA server stopped; saved records remain.')
    elif (settings.data_dir / 'server.pid').exists() and os.name != 'nt':
        # Upgrade compatibility for the earlier Bash launcher. Windows never
        # signals a process identified only by an old PID file.
        try:
            pid = int((settings.data_dir / 'server.pid').read_text())
            legacy = psutil.Process(pid)
            command = legacy.cmdline()
            if 'backend.app.main:app' in command and str(ROOT) in command and legacy.cwd() == str(ROOT):
                legacy.terminate()
                wait_stopped(legacy, timeout=30)
                (settings.data_dir / 'server.pid').unlink(missing_ok=True)
                print('Previous Mac server stopped.')
        except (ValueError, psutil.NoSuchProcess):
            pass
    else:
        print('No running server owned by this launcher.')
    ollama_file = settings.data_dir / 'ollama-process.json'
    ollama_state = read_state(ollama_file)
    # Recognize the timestamp + executable record written by the old Mac
    # launcher once, then upgrade to precise cross-platform process identity.
    if os.name != 'nt' and 'created' not in ollama_state and isinstance(ollama_state.get('pid'), int):
        try:
            prior = psutil.Process(ollama_state['pid'])
            command = prior.cmdline()
            if (ollama_state.get('started') == time.asctime(time.localtime(prior.create_time()))
                    and len(command) >= 2 and command[1] == 'serve'
                    and Path(command[0]).resolve() == Path(ollama_state.get('binary', '')).resolve()):
                ollama_state = identity(prior.pid)
                write_state(ollama_file, ollama_state)
        except (psutil.Error, OSError):
            pass
    ollama = owned_process(ollama_state)
    if ollama:
        ollama.terminate()
        try:
            wait_stopped(ollama, timeout=15)
        except psutil.TimeoutExpired:
            raise RuntimeError('Ollama is still stopping. Run Stop again shortly.')
        ollama_file.unlink(missing_ok=True)
        print("NEUAURA's Ollama process stopped.")
    elif ollama_state:
        print('Ollama is not owned by this launcher; it was left running.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'stop', 'status', 'copy-setup-token'])
    parser.add_argument('--no-open', action='store_true')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port must be between 1 and 65535')
    os.umask(0o077)
    settings = Settings()
    private_directory(settings.data_dir)
    (settings.data_dir / 'logs').mkdir(exist_ok=True)
    with FileLock(str(settings.data_dir / 'desktop-launch.lock'), timeout=60):
        if args.action == 'start':
            start(settings, not args.no_open, args.port)
        elif args.action == 'stop':
            stop(settings)
        elif args.action == 'status':
            health = get_json(f'http://127.0.0.1:{args.port}/api/v1/health')
            print('NEUAURA: ' + ('running' if health else 'stopped'))
            print('Ollama: ' + ('running' if get_json(settings.llm_base_url.rstrip('/') + '/api/tags') else 'stopped'))
            print(f'Project: {ROOT}\nData and logs: {settings.data_dir}')
            if not health:
                raise SystemExit(1)
        else:
            token = settings.data_dir / 'setup-token'
            if not token.exists():
                print(f'Workspace already configured, or not started yet. Open http://localhost:{args.port}.')
                return
            command = ['clip.exe'] if os.name == 'nt' else ['/usr/bin/pbcopy']
            # clip.exe reads UTF-16LE; the token itself is never printed.
            content = token.read_text().strip()
            subprocess.run(command, input=content.encode('utf-16le' if os.name == 'nt' else 'utf-8'), check=True)
            print('Setup token copied. Paste into the Setup token field; it is not your password.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('NEUAURA: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
