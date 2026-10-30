"""Install shortcuts without merging into an unrelated Desktop project folder."""
import base64
import json
import os
from pathlib import Path
import shlex
import subprocess
from runtime import ROOT, venv_python


def powershell(script, **variables):
    return subprocess.check_output(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand',
         base64.b64encode(script.encode('utf-16le')).decode('ascii')],
        env={**os.environ, **variables}, timeout=30,
        **({'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}),
    ).decode('utf-8-sig').strip()


def desktop_folder():
    if os.name == 'nt':
        folder = powershell("[Console]::OutputEncoding = [Text.Encoding]::UTF8; [Environment]::GetFolderPath('Desktop')")
        if not folder:
            raise RuntimeError('Cannot locate your Windows Desktop.')
        return Path(folder)
    return Path.home() / 'Desktop'


def install(folder=None):
    desktop = (folder or desktop_folder()) / 'NEUAURA B2B'
    marker = desktop / '.neuaura-b2b-shortcuts'
    if desktop.exists() and (not marker.exists() or marker.read_text(encoding='utf-8').strip() != str(ROOT)):
        raise RuntimeError('The NEUAURA B2B Desktop folder belongs to another project. Rename that shortcut folder before installing.')
    desktop.mkdir(parents=True, exist_ok=True)
    marker.write_text(str(ROOT) + '\n', encoding='utf-8')
    if os.name == 'nt':
        powershell(r"""
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
foreach ($name in @('Start NEUAURA', 'Stop NEUAURA', 'Copy setup token')) {
  $link = $shell.CreateShortcut((Join-Path $env:NEUAURA_DESKTOP ($name + '.lnk')))
  $link.TargetPath = Join-Path $env:NEUAURA_PROJECT ($name + '.cmd')
  $link.WorkingDirectory = $env:NEUAURA_PROJECT
  $link.Save()
}
$files = $shell.CreateShortcut((Join-Path $env:NEUAURA_DESKTOP 'Project files.lnk'))
$files.TargetPath = $env:NEUAURA_PROJECT
$files.Save()
""", NEUAURA_DESKTOP=str(desktop), NEUAURA_PROJECT=str(ROOT))
        start_name = 'Start NEUAURA'
        stop_name = 'Stop NEUAURA'
        token_name = 'Copy setup token'
    else:
        for filename, action in [('Start NEUAURA.command', 'start'), ('Stop NEUAURA.command', 'stop'), ('Copy setup token.command', 'copy-setup-token')]:
            content = '#!/bin/bash\ncd ' + shlex.quote(str(ROOT)) + '\nexport PYTHONUTF8=1\n' + shlex.quote(str(venv_python())) + ' scripts/desktop.py ' + action + '\nresult=$?\nprintf "\\nYou may close this window. Press Enter to finish.\\n"\nread -r unused\nexit "$result"\n'
            file = desktop / filename
            file.write_text(content, encoding='utf-8')
            file.chmod(0o755)
        link = desktop / 'Project files'
        if not link.exists() and not link.is_symlink():
            link.symlink_to(ROOT, target_is_directory=True)
        start_name, stop_name, token_name = 'Start NEUAURA.command', 'Stop NEUAURA.command', 'Copy setup token.command'
    (desktop / 'NEUAURA.code-workspace').write_text(json.dumps({
        'folders': [{'path': str(ROOT)}],
        'settings': {'python.defaultInterpreterPath': str(ROOT / '.venv')}
    }, indent=2) + '\n', encoding='utf-8')
    (desktop / 'START HERE.txt').write_text(
        f'NEUAURA B2B\n\nDouble-click {start_name}.\nOpen http://localhost:8000.\n'
        f'First time: run {token_name}, paste into Setup token, then choose your own email/password.\n'
        f'Double-click {stop_name} to stop.\n\nProject: {ROOT}\n'
        'Data is in local-data unless you changed NEUAURA_DATA_DIR in .env.\n'
        'Windows instructions: docs/WINDOWS_SETUP.md. Mac instructions: docs/START_HERE.md.\n', encoding='utf-8')
    print('Desktop shortcuts ready: ' + str(desktop))


if __name__ == '__main__':
    install()
