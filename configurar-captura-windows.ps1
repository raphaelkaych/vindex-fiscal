# Início automático da captura após entrar no Windows, para o usuário atual.
# Não pede certificado/senha, não usa administrador e não inicia consultas agora.
[CmdletBinding()]
param(
    [switch]$Remover
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$taskName = 'Vindex Fiscal - Captura'
$taskPath = '\'
$projectRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)

if ($env:OS -ne 'Windows_NT') {
    throw 'Este script configura o Agendador de Tarefas do Windows.'
}

try {
    $registered = Get-ScheduledTask -TaskName $taskName -TaskPath $taskPath -ErrorAction SilentlyContinue
    if ($null -ne $registered) {
        $registeredRoot = [string]($registered.Actions | Select-Object -First 1).WorkingDirectory
        if ($registeredRoot.TrimEnd('\') -ine $projectRoot.TrimEnd('\')) {
            throw 'Já existe uma tarefa com este nome vinculada a outra pasta. Nenhuma tarefa foi alterada.'
        }
    }
    if ($Remover) {
        $existing = Get-ScheduledTask -TaskName $taskName -TaskPath $taskPath -ErrorAction SilentlyContinue
        if ($null -eq $existing) {
            Write-Host 'A tarefa de captura do Vindex Fiscal não está registrada.'
            return
        }
        if ($existing.State -eq 'Running') {
            Stop-ScheduledTask -TaskName $taskName -TaskPath $taskPath
        }
        Unregister-ScheduledTask -TaskName $taskName -TaskPath $taskPath -Confirm:$false
        Write-Host 'Tarefa removida. Os certificados, dados, autorizações e NSUs foram preservados.'
        Write-Host 'A captura continua disponível ao executar: py iniciar.py'
        return
    }

    $pythonWindowless = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
    $captureHelper = Join-Path $projectRoot 'tools\capture_background.py'
    if (-not (Test-Path -LiteralPath $pythonWindowless -PathType Leaf)) {
        throw 'O ambiente Python ainda não está preparado. Execute py iniciar.py --preparar nesta pasta e tente novamente.'
    }
    if (-not (Test-Path -LiteralPath $captureHelper -PathType Leaf)) {
        throw 'O arquivo tools\capture_background.py não foi encontrado nesta instalação.'
    }

    $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $action = New-ScheduledTaskAction -Execute $pythonWindowless `
        -Argument ('"' + $captureHelper + '"') -WorkingDirectory $projectRoot
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
    $principal = New-ScheduledTaskPrincipal -UserId $currentUser `
        -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
        -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

    $definition = New-ScheduledTask -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings `
        -Description 'Captura de leitura DF-e do Vindex Fiscal para empresas previamente autorizadas. Inicia no logon deste usuário e mantém NSUs e limites no banco local.'
    Register-ScheduledTask -TaskName $taskName -TaskPath $taskPath `
        -InputObject $definition -Force | Out-Null

    Write-Host 'Captura configurada para iniciar automaticamente após entrar no Windows com este usuário.'
    Write-Host 'A tarefa usa permissões normais do usuário e não guarda senha de Windows ou de certificado.'
    Write-Host 'O computador precisa estar ligado, conectado e com este usuário conectado.'
    Write-Host 'O registro não iniciou uma consulta agora. Para iniciar o processo neste logon, use:'
    Write-Host "  Start-ScheduledTask -TaskName '$taskName'"
    Write-Host 'Para conferir a tarefa:'
    Write-Host "  Get-ScheduledTask -TaskName '$taskName'"
    Write-Host 'Log local: tmp\capture-worker.log'
    Write-Host 'Para remover a inicialização automática:'
    Write-Host '  powershell -NoProfile -ExecutionPolicy Bypass -File .\configurar-captura-windows.ps1 -Remover'
}
catch {
    $message = $_.Exception.Message
    if (($_.Exception -is [System.UnauthorizedAccessException]) -or
        ($_.Exception.HResult -eq -2147024891) -or
        ($message -match 'Access.+denied|Acesso.+negado|0x80070005')) {
        Write-Error ('O Windows negou acesso ao Agendador de Tarefas. A política deste computador pode exigir que um administrador autorize o registro desta tarefa para o seu usuário. Erro do Windows: ' + $message)
    }
    else {
        Write-Error ('Não foi possível configurar a tarefa do Vindex Fiscal. ' + $message)
    }
    exit 1
}
