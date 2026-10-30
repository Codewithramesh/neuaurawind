"""Create this machine's environment. Existing .env, database, accounts and models are preserved."""
import argparse
import os
from pathlib import Path
import platform
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-shortcuts', action='store_true')
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError('Use Python 3.12: Windows: py -3.12 scripts/setup.py; macOS: python3.12 scripts/setup.py')
    if os.name == 'nt' and (struct.calcsize('P') != 8 or platform.machine().upper() not in {'AMD64', 'X86_64'}):
        raise RuntimeError('Native Windows x64 Python is required. Windows ARM64 and 32-bit Python are not supported.')
    os.umask(0o077)
    os.chdir(ROOT)
    python = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists():
        if (ROOT / '.venv').exists():
            raise RuntimeError('This .venv belongs to another OS or is incomplete. Rename/remove only .venv, then rerun setup. Keep .env and local-data.')
        subprocess.run([sys.executable, '-m', 'venv', str(ROOT / '.venv')], check=True)
    result = subprocess.run([str(python), '-c', 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'], capture_output=True, text=True, check=True)
    if result.stdout.strip() != '3.12':
        raise RuntimeError('The existing .venv must use Python 3.12. Recreate only .venv; keep your data.')
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(ROOT / 'backend/requirements.txt')], check=True)
    if not (ROOT / '.env').exists():
        with (ROOT / '.env').open('x', encoding='utf-8') as output:
            output.write((ROOT / '.env.example').read_text(encoding='utf-8'))
        if os.name != 'nt':
            (ROOT / '.env').chmod(0o600)
    # Imported only after pip installs dependencies. Keep the bootstrap stdlib-only.
    subprocess.run([str(python), str(ROOT / 'scripts/manage.py'), 'build'], check=True)
    subprocess.run([str(python), '-m', 'alembic', '-c', str(ROOT / 'backend/alembic.ini'), 'upgrade', 'head'], check=True)
    if not args.no_shortcuts:
        subprocess.run([str(python), str(ROOT / 'scripts/install_desktop_shortcuts.py')], check=True)
    print('\nSetup complete. Run Start NEUAURA.cmd (Windows) or the Desktop Start NEUAURA.command (Mac).')
    print('Download models explicitly using scripts/download-models.cmd (Windows), or python scripts/manage.py models inside .venv.')


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:
        print('NEUAURA setup: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
