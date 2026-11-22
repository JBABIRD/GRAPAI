<# Removes GRAPAI for this user: the install folder (app, ComfyUI, models, your board data) and the shortcuts. #>
$Root = $PSScriptRoot
Write-Host "This removes GRAPAI from $Root, including all models and the images on your boards." -ForegroundColor Yellow
$keep = Read-Host "Type YES to remove everything, or KEEP to remove everything except your board data (data folder)"
if ($keep -ne "YES" -and $keep -ne "KEEP") { Write-Host "Nothing removed."; Read-Host "Press Enter to close"; exit 0 }
Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($Root, [StringComparison]::OrdinalIgnoreCase) } |
    Stop-Process -Force -ErrorAction SilentlyContinue
Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path ([Environment]::GetFolderPath("Desktop")) "GRAPAI.lnk")
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path ([Environment]::GetFolderPath("Programs")) "GRAPAI")
Set-Location $env:TEMP
Get-ChildItem -Force $Root | Where-Object { -not ($keep -eq "KEEP" -and $_.Name -eq "data") } |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
if ($keep -eq "YES") { Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $Root }
Write-Host "GRAPAI has been removed." -ForegroundColor Green
Read-Host "Press Enter to close"
