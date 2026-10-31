"""Keep the Windows entry-point compatible with Windows PowerShell 5.1."""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
script = (root / 'installer/windows.ps1').read_bytes()
assert script.startswith(b'\xef\xbb\xbf'), 'Windows PowerShell 5.1 requires a UTF-8 BOM for the trilingual bootstrap'
text=script.decode('utf-8-sig')
assert '需要 64 位 Windows。' in text and '[Console]::OutputEncoding' in text
assert not any(char in text for char in '“”‘’'), 'Use ordinary PowerShell quote delimiters'
assert (root/'Windows.cmd').read_bytes().isascii()
workflow = (root / '.github/workflows/check.yml').read_text()
assert 'shell: powershell' in workflow, 'Parse with the same Windows PowerShell used by Windows.cmd'
print('PASS Windows bootstrap encoding and parser CI regression checks')
