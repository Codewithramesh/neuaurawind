"""Private local directories on POSIX and Windows (where chmod does not set ACLs)."""
import base64
import os
from pathlib import Path
import subprocess


def private_directory(path: Path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        path.chmod(0o700)
        return
    # Pass the path as data, so spaces, Unicode, apostrophes and shell characters
    # in a Windows profile name cannot become PowerShell code.
    script = r"""+$ErrorActionPreference = 'Stop'
$acl = [System.Security.AccessControl.DirectorySecurity]::new()
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$system = [System.Security.Principal.SecurityIdentifier]::new('S-1-5-18')
$acl.SetOwner($user)
$acl.SetAccessRuleProtection($true, $false)
foreach ($identity in @($user, $system)) {
  $rule = [System.Security.AccessControl.FileSystemAccessRule]::new($identity, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
  $acl.AddAccessRule($rule)
}
Set-Acl -LiteralPath $env:NEUAURA_PRIVATE_DIRECTORY -AclObject $acl
"""
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand",
         base64.b64encode(script.encode("utf-16le")).decode("ascii")],
        env={**os.environ, "NEUAURA_PRIVATE_DIRECTORY": str(path.resolve())},
        capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode:
        raise RuntimeError("Cannot protect the data folder. Use a private local NTFS folder; see docs/WINDOWS_SETUP.md.")
