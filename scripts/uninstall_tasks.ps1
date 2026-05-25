# ============================================================================
#  uninstall_tasks.ps1
#
#  Esborra del Task Scheduler les tasques creades per install_tasks.ps1.
#  No esborra cap dada ni cap log — només les entrades del programador.
#
#  Ús (com a ADMINISTRADOR):
#      powershell -ExecutionPolicy Bypass -File scripts\uninstall_tasks.ps1
# ============================================================================

#Requires -RunAsAdministrator

$ErrorActionPreference = 'Stop'

$Names = @(
    'SalaFatiga - Adquisicio (Qt)',
    'SalaFatiga - Dashboard web'
)

Write-Host ""
Write-Host "=== Desinstal·lant tasques de Sala de fatiga ==="

foreach ($name in $Names) {
    $existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($existing) {
        # Si està en marxa, aturar-la abans d'esborrar.
        if ($existing.State -eq 'Running') {
            Write-Host "  · aturant '$name'..."
            Stop-ScheduledTask -TaskName $name
        }
        Write-Host "  · esborrant '$name'..."
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
    } else {
        Write-Host "  · '$name' no estava registrada (saltada)"
    }
}

Write-Host ""
Write-Host "=== Fet ==="
Write-Host ""
