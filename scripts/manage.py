"""Portable build, tests, explicit model installation and developer services."""
import argparse
import os
import subprocess
import sys
import time
from urllib.parse import urlparse
import psutil
from runtime import ROOT, Settings, npm_command, read_state, venv_python, write_state


def npm(*args):
    subprocess.run(npm_command(*args), cwd=ROOT / 'frontend', check=True)


def models():
    from desktop import ollama_binary
    settings = Settings()
    parsed = urlparse(settings.llm_base_url)
    if settings.extraction_provider != 'ollama' or parsed.hostname not in {'127.0.0.1', 'localhost'} or parsed.scheme != 'http' or parsed.path or parsed.query or parsed.username:
        raise RuntimeError('Automatic model installation is for local Ollama only. Configure your inference server separately.')
    subprocess.run([str(venv_python()), str(ROOT / 'scripts/download_model.py')], cwd=ROOT, check=True)
    subprocess.run([str(venv_python()), str(ROOT / 'scripts/desktop.py'), 'start', '--no-open'], cwd=ROOT, check=True)
    binary = ollama_binary()
    if not binary:
        raise RuntimeError('Install Ollama from https://ollama.com/download and reopen the launcher.')
    # Model storage belongs to the server answering this endpoint, including the
    # native Windows tray application. No second, conflicting model store is made.
    subprocess.run([binary, 'pull', settings.llm_model], env={**os.environ, 'OLLAMA_HOST': settings.llm_base_url}, check=True)


def dev():
    settings = Settings()
    if read_state(settings.data_dir / 'server-process.json'):
        raise RuntimeError('Stop the regular app before starting development mode.')
    server = subprocess.Popen([str(venv_python()), str(ROOT / 'scripts/run_server.py')], cwd=ROOT)
    frontend = None
    try:
        from runtime import wait_for
        wait_for('http://127.0.0.1:8000/api/v1/health', server)
        frontend = subprocess.Popen(npm_command('run', 'dev'), cwd=ROOT / 'frontend',
                                    **({'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}))
        print('App: http://localhost:8000; developer UI: http://localhost:5173. Ctrl+C stops both.', flush=True)
        while server.poll() is None and frontend.poll() is None:
            time.sleep(.5)
        raise RuntimeError('A development service exited. Inspect its output above.')
    except KeyboardInterrupt:
        pass
    finally:
        if frontend and frontend.poll() is None:
            process = psutil.Process(frontend.pid)
            children = process.children(recursive=True)
            for child in reversed(children):
                try: child.terminate()
                except psutil.NoSuchProcess: pass
            process.terminate()
            psutil.wait_procs([*children, process], timeout=10)
        if server.poll() is None:
            state = read_state(settings.data_dir / 'server-process.json')
            if state.get('pid') == server.pid:
                write_state(settings.data_dir / 'server-stop.json', {'shutdown_token': state['shutdown_token']})
            server.wait(timeout=30)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'test', 'models', 'dev'])
    args, rest = parser.parse_known_args()
    if args.action == 'build':
        version = subprocess.check_output(npm_command('--version'), text=True).strip()
        node = subprocess.check_output([npm_command()[0], '--version'], text=True).strip().lstrip('v')
        major, minor = map(int, node.split('.')[:2])
        if major < 22 or (major == 22 and minor < 12):
            raise RuntimeError('Node.js 22.12+ is required.')
        print(f'Node {node}, npm {version}', flush=True)
        npm('ci'); npm('run', 'build')
    elif args.action == 'test':
        subprocess.run([sys.executable, '-m', 'pytest', *rest], cwd=ROOT, check=True)
        npm('test'); npm('run', 'build')
    elif args.action == 'models':
        models()
    else:
        dev()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('NEUAURA: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
