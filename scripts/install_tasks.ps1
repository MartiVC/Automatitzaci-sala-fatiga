# ============================================================================
#  install_tasks.ps1
#
#  Registra al Task Scheduler de Windows les dues tasques que mantenen viu
#  el PC LAB sense necessitat d'intervenció manual:
#
#   1. "SalaFatiga - Dashboard web"  → arrenca al BOOT, com a SYSTEM.
#                                        Serveix el dashboard FastAPI encara
#                                        que ningú estigui logat.
#
#   2. "SalaFatiga - Adquisicio (Qt)" → arrenca quan l'usuari LOG IN.
#                                        L'app Qt necessita un escriptori actiu.
#
#  Ambdues es reinicien automàticament si peten (cada 1 min, 3 intents).
#
#  És IDEMPOTENT: si les tasques ja existeixen, les esborra i les recrea.
#
#  Ús:
#      # Executar com a ADMINISTRADOR:
#      powershell -ExecutionPolicy Bypass -File scripts\install_tasks.ps1
#
#  Per desregistrar-les: scripts\uninstall_tasks.ps1
# ============================================================================

#Requires -RunAsAdministrator

$ErrorActionPreference = 'Stop'

# Resol l'arrel del repo a partir d'aquest script.
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoDir   = Resolve-Path (Join-Path $ScriptDir '..')

$AppBat = Join-Path $RepoDir 'scripts\run_app_service.bat'
$WebBat = Join-Path $RepoDir 'scripts\run_web_service.bat'

if (-not (Test-Path $AppBat)) { throw "No s'ha trobat $AppBat" }
if (-not (Test-Path $WebBat)) { throw "No s'ha trobat $WebBat" }

$AppTaskName = 'SalaFatiga - Adquisicio (Qt)'
$WebTaskName = 'SalaFatiga - Dashboard web'

function Remove-IfExists($name) {
    $existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "  · esborrant tasca existent '$name'..."
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
    }
}

Write-Host ""
Write-Host "=== Instal·lant tasques de Sala de fatiga ==="
Write-Host "Repositori: $RepoDir"
Write-Host ""

# ---------------------------------------------------------------------------
#  1. Dashboard web — arrenca al boot, com a SYSTEM, sense sessió interactiva.
# ---------------------------------------------------------------------------
Write-Host "[1/2] Tasca: $WebTaskName"
Remove-IfExists $WebTaskName

$webAction    = New-ScheduledTaskAction -Execute $WebBat
$webTrigger   = New-ScheduledTaskTrigger -AtStartup
$webPrincipal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$webSettings  = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -RestartCount 3 `
    -ExecutionTimeLimit ([TimeSpan]::Zero)   # 0 = sense límit (servei perpetu)

Register-ScheduledTask `
    -TaskName    $WebTaskName `
    -Description 'Dashboard FastAPI de consulta remota del PC LAB de la sala de fatiga.' `
    -Action      $webAction `
    -Trigger     $webTrigger `
    -Principal   $webPrincipal `
    -Settings    $webSettings | Out-Null
Write-Host "  · registrada (trigger: AtStartup, usuari: SYSTEM)"

# ---------------------------------------------------------------------------
#  2. App Qt — arrenca quan l'usuari fa login (necessita escriptori actiu).
# ---------------------------------------------------------------------------
Write-Host "[2/2] Tasca: $AppTaskName"
Remove-IfExists $AppTaskName

$currentUser = "$env:USERDOMAIN\$env:USERNAME"

$appAction    = New-ScheduledTaskAction -Execute $AppBat
$appTrigger   = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$appPrincipal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
$appSettings  = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -RestartCount 3 `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask `
    -TaskName    $AppTaskName `
    -Description "App Qt d'adquisicio i supervisio del PC LAB de la sala de fatiga." `
    -Action      $appAction `
    -Trigger     $appTrigger `
    -Principal   $appPrincipal `
    -Settings    $appSettings | Out-Null
Write-Host "  · registrada (trigger: AtLogOn de $currentUser)"

Write-Host ""
Write-Host "=== Fet ==="
Write-Host "Comprova-les amb:"
Write-Host "    Get-ScheduledTask -TaskName 'SalaFatiga*' | Format-Table TaskName, State"
Write-Host ""
Write-Host "Per arrencar-les ara mateix sense esperar trigger:"
Write-Host "    Start-ScheduledTask -TaskName '$WebTaskName'"
Write-Host "    Start-ScheduledTask -TaskName '$AppTaskName'"
Write-Host ""
Write-Host "Logs de stdout/stderr:"
Write-Host "    logs\run_app_stdout.log"
Write-Host "    logs\run_web_stdout.log"
Write-Host ""
