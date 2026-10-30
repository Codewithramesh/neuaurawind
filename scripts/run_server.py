"""Single local server with a file-based graceful shutdown on both operating systems."""
import argparse
import os
import secrets
import subprocess
import threading
from filelock import FileLock, Timeout
from runtime import ROOT, Settings, get_json, identity, private_directory, read_state, write_state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port must be between 1 and 65535')
    os.umask(0o077)
    settings = Settings()
    private_directory(settings.data_dir)
    state_file = settings.data_dir / 'server-process.json'
    stop_file = settings.data_dir / 'server-stop.json'
    with FileLock(str(settings.data_dir / 'server.lock'), timeout=0):
        if get_json(f'http://127.0.0.1:{args.port}/api/v1/health', 1):
            raise RuntimeError('Port is already serving an application. Stop that application first.')
        if not (ROOT / 'frontend/dist/index.html').is_file():
            raise RuntimeError('Build the dashboard first: run the setup script.')
        subprocess.run([os.sys.executable, '-m', 'alembic', '-c', str(ROOT / 'backend/alembic.ini'), 'upgrade', 'head'], cwd=ROOT, check=True)
        import uvicorn
        server = uvicorn.Server(uvicorn.Config('backend.app.main:app', host='127.0.0.1', port=args.port,
                                               workers=1, loop='asyncio'))
        secret = secrets.token_hex(32)
        state = {**identity(os.getpid()), 'shutdown_token': secret, 'port': args.port}
        stop_file.unlink(missing_ok=True)
        write_state(state_file, state)
        finished = threading.Event()

        def watch():
            while not finished.wait(.2):
                if read_state(stop_file).get('shutdown_token') == secret:
                    server.should_exit = True
                    return

        watcher = threading.Thread(target=watch, name='neuaura-shutdown', daemon=True)
        watcher.start()
        try:
            print(f'NEUAURA: http://localhost:{args.port} — Ctrl+C or the Stop launcher shuts down.', flush=True)
            server.run()
        finally:
            finished.set()
            watcher.join(timeout=1)
            if read_state(state_file).get('shutdown_token') == secret:
                state_file.unlink(missing_ok=True)
                stop_file.unlink(missing_ok=True)


if __name__ == '__main__':
    try:
        main()
    except Timeout:
        print('NEUAURA: Another server owns this data folder. Stop it before starting a second instance.', file=os.sys.stderr)
        raise SystemExit(1)
    except Exception as exc:
        print('NEUAURA: ' + str(exc), file=os.sys.stderr)
        raise SystemExit(1)
