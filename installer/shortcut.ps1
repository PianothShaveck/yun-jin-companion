param([Parameter(Mandatory=$true)][string]$Python,[Parameter(Mandatory=$true)][string]$Program)
$ErrorActionPreference = 'Stop'
$Shell = New-Object -ComObject WScript.Shell
$Desktop = [Environment]::GetFolderPath('Desktop')
$Links = @((Join-Path $Desktop 'Yun Jin Companion.lnk'), (Join-Path ([Environment]::GetFolderPath('Programs')) 'Yun Jin Companion.lnk'))
foreach ($Link in $Links) {
    $Shortcut = $Shell.CreateShortcut($Link)
    $Shortcut.TargetPath = $Python
    $Shortcut.Arguments = '"' + (Join-Path $Program 'app\yun_jin_pet.py') + '"'
    $Shortcut.WorkingDirectory = $Program
    $Shortcut.IconLocation = (Join-Path $Program 'app\favicon.ico') + ',0'
    $Shortcut.Description = 'Yun Jin Companion - appunti, tempo e musica'
    $Shortcut.Save()
}
