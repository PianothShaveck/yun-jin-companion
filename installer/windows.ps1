$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Project = Split-Path $PSScriptRoot -Parent
$Runtime = Join-Path $env:LOCALAPPDATA 'YunJinPet\python-3.13'
function Find-Python {
    $Candidates = New-Object System.Collections.Generic.List[string]
    $Candidates.Add((Join-Path $Runtime 'python.exe'))
    $Launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($Launcher) {
        try {
            $Found = & $Launcher.Source -3 -c 'import sys; print(sys.executable)' 2>$null
            if ($LASTEXITCODE -eq 0 -and $Found) { $Candidates.Add([string]$Found) }
        } catch { } 
    }
    foreach ($Registry in @('HKCU:\Software\Python\PythonCore','HKLM:\Software\Python\PythonCore')) {
        if (Test-Path $Registry) {
            foreach ($Version in Get-ChildItem $Registry) {
                $Key = Join-Path $Version.PSPath 'InstallPath'
                if (Test-Path $Key) {
                    $Value = (Get-Item $Key).GetValue('ExecutablePath')
                    if (-not $Value) { $Value = Join-Path ((Get-Item $Key).GetValue('')) 'python.exe' }
                    if ($Value) { $Candidates.Add([string]$Value) }
                }
            }
        }
    }
    $Command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($Command -and $Command.Source -notlike '*\WindowsApps\*') { $Candidates.Add($Command.Source) }
    foreach ($Candidate in ($Candidates | Select-Object -Unique)) {
        if (Test-Path -LiteralPath $Candidate) {
            & $Candidate -c 'import sys; sys.exit(0 if (3,11)<=sys.version_info[:2]<(3,15) and sys.maxsize>2**32 else 1)' 2>$null
            if ($LASTEXITCODE -eq 0) { return $Candidate }
        }
    }
    return $null
}
try {
    if (-not [Environment]::Is64BitOperatingSystem) { throw 'Serve Windows a 64 bit.' }
    $Python = Find-Python
    if (-not $Python) {
        Write-Host 'Scarico Python 3.13 dal sito ufficiale e verifico la sua integrita...'
        $Download = Join-Path ([IO.Path]::GetTempPath()) ('yun-jin-python-' + [guid]::NewGuid().ToString() + '.exe')
        try {
            Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.13.15/python-3.13.15-amd64.exe' -OutFile $Download
            $Expected = 'edec09c4853aeae9ac36efb8c9f95b6b8e2fee65eee56d9767a8b7c69c574403'
            if ((Get-FileHash -LiteralPath $Download -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Expected) { throw 'Verifica SHA256 di Python fallita. Il file non verra eseguito.' }
            $Arguments = '/passive InstallAllUsers=0 Include_pip=1 Include_launcher=0 Include_test=0 Include_doc=0 Include_tcltk=0 PrependPath=0 Shortcuts=0 TargetDir="' + $Runtime + '"'
            $Process = Start-Process -FilePath $Download -ArgumentList $Arguments -Wait -PassThru
            if ($Process.ExitCode -notin @(0,3010)) { throw ('Installazione Python terminata con codice ' + $Process.ExitCode) }
        } finally { if (Test-Path -LiteralPath $Download) { Remove-Item -LiteralPath $Download -Force } }
        $Python = Find-Python
        if (-not $Python) { throw 'Python non trovato. Installa Python 3.13 a 64 bit da python.org e riapri questo file.' }
    }
    & $Python (Join-Path $PSScriptRoot 'install.py')
    if ($LASTEXITCODE -ne 0) { throw 'Chiudi eventuali istanze di Yun Jin e controlla il messaggio qui sopra.' }
} catch {
    Write-Host ('ERRORE: ' + $_.Exception.Message) -ForegroundColor Red
    Read-Host 'Premi Invio per chiudere'
    exit 1
}
