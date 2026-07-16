# ตัวติดตั้ง "Mail Uploader"
# วิธีใช้: คลิกขวาไฟล์นี้ > Run with PowerShell (หรือรันจาก PowerShell: .\install.ps1)
# ทำสิ่งนี้: คัดลอก exe ไปไว้ที่ %LOCALAPPDATA%\Programs แล้วสร้าง shortcut บน Desktop และ Start Menu

$ErrorActionPreference = "Stop"

$AppName = "Mail Uploader"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceExe = Join-Path $ScriptDir "dist\$AppName.exe"

if (-not (Test-Path $SourceExe)) {
    Write-Host "ไม่พบไฟล์ $SourceExe" -ForegroundColor Red
    Write-Host "กรุณา build exe ก่อนด้วยคำสั่ง PyInstaller (ดูใน SKILL.md)" -ForegroundColor Yellow
    exit 1
}

$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\$AppName"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

$TargetExe = Join-Path $InstallDir "$AppName.exe"
Copy-Item -Path $SourceExe -Destination $TargetExe -Force

Write-Host "ติดตั้งแอปไว้ที่: $InstallDir" -ForegroundColor Green

$Shell = New-Object -ComObject WScript.Shell

# Desktop shortcut
$DesktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "$AppName.lnk"
$sc = $Shell.CreateShortcut($DesktopShortcut)
$sc.TargetPath = $TargetExe
$sc.WorkingDirectory = $InstallDir
$sc.IconLocation = $TargetExe
$sc.Save()
Write-Host "สร้าง shortcut บน Desktop แล้ว" -ForegroundColor Green

# Start Menu shortcut
$StartMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$StartMenuShortcut = Join-Path $StartMenuDir "$AppName.lnk"
$sc2 = $Shell.CreateShortcut($StartMenuShortcut)
$sc2.TargetPath = $TargetExe
$sc2.WorkingDirectory = $InstallDir
$sc2.IconLocation = $TargetExe
$sc2.Save()
Write-Host "สร้าง shortcut ใน Start Menu แล้ว" -ForegroundColor Green

Write-Host ""
Write-Host "ติดตั้งเสร็จสมบูรณ์ เปิดแอปได้จาก Desktop หรือ Start Menu" -ForegroundColor Cyan
Write-Host "หมายเหตุ: ค่า To/CC/โฟลเดอร์ Advice ตั้งค่าแยกได้ในหน้า 'ตั้งค่า' ของแอป โดยไม่ต้องแก้โค้ด" -ForegroundColor Cyan
