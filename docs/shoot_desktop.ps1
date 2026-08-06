# Capture the Windows client screens.
#
# The app renders its own visual tree to PNG (--shot), because
# Graphics.CopyFromScreen comes back blank for DWM-composited WPF windows.
#
# Point it at a demo server so the shots hold sample data, not a real estate:
#   BOTHY_DEMO=1 python -m bothy.cli serve --port 8760
#   powershell -File docs/shoot_desktop.ps1
param(
  [string]$Exe = "C:\bothy\desktop\bin\Release\net8.0-windows\Bothy.exe",
  [string]$Out = "C:\bothy\docs\screenshots",
  [string]$Api = "http://127.0.0.1:8760"
)

$env:BOTHY_API = $Api
New-Item -ItemType Directory -Force -Path $Out | Out-Null

$screens = @(
  @{ Screen = "main";     File = "D1-main-window.png";         Wait = 12 },
  @{ Screen = "deploy";   File = "D2-deploy-wizard.png";       Wait = 8 },
  @{ Screen = "monitor";  File = "D3-monitor.png";             Wait = 8 },
  @{ Screen = "provider"; File = "D4-provider-properties.png"; Wait = 8 },
  @{ Screen = "tray";     File = "D5-tray-toast.png";          Wait = 8 }
)

foreach ($s in $screens) {
  $dest = Join-Path $Out $s.File
  Remove-Item $dest -ErrorAction SilentlyContinue
  $p = Start-Process -FilePath $Exe -PassThru `
       -ArgumentList "--screen", $s.Screen, "--shot", $dest
  # the app writes the capture and shuts itself down
  if (-not $p.WaitForExit($s.Wait * 1000)) { $p.Kill() }
  if (Test-Path $dest) {
    "  {0}  ({1:N0} bytes)" -f $s.File, (Get-Item $dest).Length
  } else {
    "  {0}  MISSING" -f $s.File
  }
}
