$ErrorActionPreference = 'Stop'
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) {
    $compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe'
}
Push-Location $PSScriptRoot
try {
    & $compiler /nologo /target:winexe /optimize+ /codepage:65001 '/out:步进电机简易控制.exe' /reference:System.dll /reference:System.Core.dll /reference:System.Drawing.dll /reference:System.Windows.Forms.dll src\Protocol.cs src\StepperApp.cs
    if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
    Write-Output 'Build succeeded.'
} finally { Pop-Location }
