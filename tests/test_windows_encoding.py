"""Keep the Windows entry-point compatible with Windows PowerShell 5.1."""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
script = (root / 'installer/windows.ps1').read_bytes()
assert script.isascii(), 'Bootstrap must use ASCII to avoid smart-quote and legacy encoding bugs'
assert b'verifico la sua integrita' in script
workflow = (root / '.github/workflows/check.yml').read_text()
assert 'shell: powershell' in workflow, 'Parse with the same Windows PowerShell used by Windows.cmd'
print('PASS Windows bootstrap encoding and parser CI regression checks')
