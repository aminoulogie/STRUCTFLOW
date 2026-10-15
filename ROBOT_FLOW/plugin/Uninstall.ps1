# Run from elevated 64-bit Windows PowerShell, with Robot closed.
$ErrorActionPreference = 'Stop'
if (Get-Process robot -ErrorAction SilentlyContinue) { throw 'Close Robot first.' }
$dll = Join-Path $PSScriptRoot 'bin\GCStructFlow.Robot.dll'
if (-not (Test-Path $dll)) { throw 'Keep the installed DLL until it has been unregistered.' }
$regasm = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\RegAsm.exe'
& $regasm $dll /unregister
if ($LASTEXITCODE -ne 0) { throw 'Unregistration failed. Run elevated Windows PowerShell.' }
$guid='{B15C748C-AD54-4D23-9A8A-23BFA175CA80}'
foreach ($key in @("HKCU:\Software\Autodesk\Structural\RSA\AddIns\$guid", "HKCU:\Software\Autodesk\Structural\RSA\MenuExtension\GCStructFlow Robot #$guid")) {
    if (Test-Path $key) { Remove-Item -LiteralPath $key -Recurse }
}
Write-Host 'GCStructFlow Robot unregistered. Project and settings files were not changed.'
