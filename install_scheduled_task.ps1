param(
    [string]$TaskName = "PriceAI-Price-Monitor",
    [int]$IntervalMinutes = 5
)

$ErrorActionPreference = "Stop"
if ($IntervalMinutes -lt 1) {
    throw "IntervalMinutes must be at least 1."
}

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = if (Get-Command python -ErrorAction SilentlyContinue) {
    (Get-Command python).Source
} else {
    throw "Python 3 was not found. Install Python and try again."
}

$ScriptPath = Join-Path $ProjectDir "price_monitor.py"
$ConfigPath = Join-Path $ProjectDir "config.json"
$StatePath = Join-Path $ProjectDir "monitor_state.json"
$Arguments = "`"$ScriptPath`" --config `"$ConfigPath`" --state `"$StatePath`" check"

$Action = New-ScheduledTaskAction -Execute $Python -Argument $Arguments -WorkingDirectory $ProjectDir
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 2)

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings `
    -Description "Check PriceAI ChatGPT Plus offers and send price alerts" -Force | Out-Null

Write-Host "Scheduled task installed: $TaskName (every $IntervalMinutes minutes)"
Write-Host "Remove it with: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
