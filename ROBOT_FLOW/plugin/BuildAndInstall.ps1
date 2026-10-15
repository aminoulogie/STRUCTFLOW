# Build against the Robot SDK already installed on this computer.
# Building is the default. -Install explicitly registers the add-in and needs elevation.
[CmdletBinding()]
param(
    [string]$RobotDll,
    [string]$PythonExe,
    [switch]$Install
)
$ErrorActionPreference = 'Stop'
if (-not [Environment]::Is64BitProcess) { throw 'Run 64-bit Windows PowerShell.' }
if (-not $RobotDll) {
    $base = Join-Path $env:ProgramFiles 'Autodesk\Robot Structural Analysis Professional 2027'
    $RobotDll = @((Join-Path $base 'Exe\Interop.RobotOM.dll'), (Join-Path $base 'System\Exe\Interop.RobotOM.dll')) |
        Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $RobotDll -or -not (Test-Path $RobotDll)) { throw 'Pass -RobotDll with the full path to Robot 2027 Interop.RobotOM.dll.' }
if (-not $PythonExe) { $PythonExe = (Get-Command python.exe -ErrorAction Stop).Source }
$PythonExe = (Resolve-Path $PythonExe).Path
& $PythonExe -c "import sys, struct, tkinter, pythonnet; assert sys.version_info >= (3,10); assert struct.calcsize('P') == 8; pythonnet.load('netfx')"
if ($LASTEXITCODE -ne 0) { throw 'Use 64-bit Python 3.10+ with Tk and pythonnet 3 (see README).' }
$framework = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319'
$csc = Join-Path $framework 'csc.exe'
if (-not (Test-Path $csc)) { throw '.NET Framework 4.x compiler is missing.' }
$bin = Join-Path $PSScriptRoot 'bin'
New-Item -ItemType Directory -Force -Path $bin | Out-Null
$dll = Join-Path $bin 'GCStructFlow.Robot.dll'
& $csc /nologo /target:library /platform:x64 "/out:$dll" "/reference:$RobotDll" /reference:System.Windows.Forms.dll (Join-Path $PSScriptRoot 'RobotAddIn.cs')
if ($LASTEXITCODE -ne 0) { throw 'Add-in compilation failed. Nothing was registered.' }
Copy-Item $RobotDll (Join-Path $bin 'Interop.RobotOM.dll') -Force
[IO.File]::WriteAllText((Join-Path $bin 'python-path.txt'), $PythonExe)
Write-Host "Built $dll"
if (-not $Install) { Write-Host 'Build only. To register, rerun with -Install from elevated Windows PowerShell.'; return }
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Registration requires elevated Windows PowerShell under your normal Windows account.' }
if (Get-Process robot -ErrorAction SilentlyContinue) { throw 'Close Robot before registering the add-in.' }
& (Join-Path $framework 'RegAsm.exe') $dll /codebase
if ($LASTEXITCODE -ne 0) { throw 'COM registration failed.' }
$guid = '{B15C748C-AD54-4D23-9A8A-23BFA175CA80}'
$key = "HKCU:\Software\Autodesk\Structural\RSA\AddIns\$guid"
New-Item -Path $key -Force | Out-Null
@{AddInsType=0;Enable=1;GuidType=2;KeepMenuGrade=0}.GetEnumerator() | ForEach-Object {
    New-ItemProperty -Path $key -Name $_.Key -Value $_.Value -PropertyType DWord -Force | Out-Null
}
@{File=$dll;Guid=$guid;KeyName=$guid;Name='GCStructFlow Robot'}.GetEnumerator() | ForEach-Object {
    New-ItemProperty -Path $key -Name $_.Key -Value $_.Value -PropertyType String -Force | Out-Null
}
$menu = "HKCU:\Software\Autodesk\Structural\RSA\MenuExtension\GCStructFlow Robot #$guid"
New-Item -Path $menu -Force | Out-Null
@{Guid=$guid;MenuName='GCStructFlow Robot'}.GetEnumerator() | ForEach-Object {
    New-ItemProperty -Path $menu -Name $_.Key -Value $_.Value -PropertyType String -Force | Out-Null
}
$tabs = @('Levels','Grids','Properties','Draw','Checks')
New-ItemProperty -Path $menu -Name MenuSize -Value $tabs.Count -PropertyType DWord -Force | Out-Null
for ($i=0; $i -lt $tabs.Count; $i++) {
    $id=$i+1
    New-ItemProperty -Path $menu -Name "CmdId#$id" -Value $id -PropertyType DWord -Force | Out-Null
    New-ItemProperty -Path $menu -Name "CmdName#$id" -Value ("GCStructFlow - " + $tabs[$i]) -PropertyType String -Force | Out-Null
}
Write-Host 'Registered for this Windows user. Start Robot and check Add-ins / Modules complémentaires.'
