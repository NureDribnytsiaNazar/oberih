<#
.SYNOPSIS
  Резервна копія тому БД розгорнутої системи (pg_dump) і перевірка відновлення.
.DESCRIPTION
  backup  — pg_dump у форматі custom у deploy/backups/oberih-<час>.dump;
  verify  — відновлює останню (або вказану) копію в тимчасову БД
            oberih_restore_check того самого контейнера, порівнює кількість
            рядків ключових таблиць і видаляє тимчасову БД.
  restore — відновлює копію в робочу БД (зупиніть api перед цим!).
  Доповнює логічні копії застосунку (/admin/backups), що лежать у томі app-data.
.EXAMPLE
  .\deploy\backup-db.ps1 backup
  .\deploy\backup-db.ps1 verify
#>
param(
    [Parameter(Mandatory = $true)][ValidateSet("backup", "verify", "restore")][string]$Action,
    [string]$File
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$compose = @("compose", "-f", (Join-Path $root "docker-compose.prod.yml"),
             "--env-file", (Join-Path $root ".env.prod"))
$dir = Join-Path $PSScriptRoot "backups"
New-Item -ItemType Directory -Force $dir | Out-Null
$tables = "users", "facilities", "nodes", "sensors", "events", "alarms", "node_commands"

function Invoke-Db([string[]]$Arguments) {
    & docker @compose exec -T db @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Команда в контейнері db завершилася з помилкою" }
}

function Get-Counts([string]$Database) {
    $query = ($tables | ForEach-Object { "SELECT '$_', count(*) FROM $_" }) -join " UNION ALL "
    Invoke-Db @("psql", "-U", "oberih", "-d", $Database, "-At", "-c", $query)
}

function Resolve-Dump {
    if ($File) { return (Resolve-Path $File).Path }
    $latest = Get-ChildItem $dir -Filter "*.dump" | Sort-Object LastWriteTime | Select-Object -Last 1
    if ($null -eq $latest) { throw "Копій у $dir немає; спочатку виконайте backup" }
    $latest.FullName
}

switch ($Action) {
    "backup" {
        $target = Join-Path $dir ("oberih-{0}.dump" -f (Get-Date -Format "yyyyMMdd-HHmmss"))
        Invoke-Db @("pg_dump", "-U", "oberih", "-d", "oberih", "-Fc", "-f", "/tmp/oberih.dump")
        & docker @compose cp db:/tmp/oberih.dump $target
        if ($LASTEXITCODE -ne 0) { throw "Не вдалося скопіювати копію з контейнера" }
        Write-Host "Копію збережено: $target"
    }
    "verify" {
        $dump = Resolve-Dump
        & docker @compose cp $dump db:/tmp/check.dump
        Invoke-Db @("dropdb", "-U", "oberih", "--if-exists", "oberih_restore_check")
        Invoke-Db @("createdb", "-U", "oberih", "oberih_restore_check")
        try {
            Invoke-Db @("pg_restore", "-U", "oberih", "-d", "oberih_restore_check", "--no-owner", "/tmp/check.dump")
            $live = Get-Counts "oberih"
            $restored = Get-Counts "oberih_restore_check"
            Write-Host "Таблиця|рядків у робочій БД / у відновленій копії:"
            for ($i = 0; $i -lt $live.Count; $i++) { Write-Host "  $($live[$i])  /  $($restored[$i])" }
            Write-Host "Відновлення з $dump перевірено."
        } finally {
            Invoke-Db @("dropdb", "-U", "oberih", "--if-exists", "oberih_restore_check")
        }
    }
    "restore" {
        $dump = Resolve-Dump
        & docker @compose cp $dump db:/tmp/restore.dump
        Invoke-Db @("pg_restore", "-U", "oberih", "-d", "oberih", "--clean", "--if-exists", "--no-owner", "/tmp/restore.dump")
        Write-Host "Робочу БД відновлено з $dump. Запустіть api: docker compose ... up -d api"
    }
}
