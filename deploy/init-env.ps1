<#
.SYNOPSIS
  Створює .env.prod із випадковими секретами (пароль БД, JWT_SECRET).
.DESCRIPTION
  Запускається один раз на машині розгортання. Наявний .env.prod не
  перезаписується без -Force: зміна пароля БД після першого запуску зробить
  наявний том БД недоступним.
.EXAMPLE
  .\deploy\init-env.ps1
  .\deploy\init-env.ps1 -HttpsPort 8443 -HttpPort 8080
#>
param(
    [int]$HttpPort = 80,
    [int]$HttpsPort = 443,
    [switch]$Force
)
$ErrorActionPreference = "Stop"

function New-Secret([int]$Bytes) {
    $buffer = New-Object byte[] $Bytes
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($buffer) } finally { $rng.Dispose() }
    # base64url: лише символи, безпечні в URL підключення до БД.
    [Convert]::ToBase64String($buffer).TrimEnd("=").Replace("+", "-").Replace("/", "_")
}

$root = Split-Path $PSScriptRoot -Parent
$target = Join-Path $root ".env.prod"
if ((Test-Path $target) -and -not $Force) {
    Write-Host "Файл $target вже існує; щоб перезаписати, додайте -Force."
    exit 1
}
$template = Get-Content (Join-Path $root ".env.prod.example") -Encoding UTF8
$lines = foreach ($line in $template) {
    switch -Regex ($line) {
        '^POSTGRES_PASSWORD=' { "POSTGRES_PASSWORD=$(New-Secret 24)" }
        '^JWT_SECRET=' { "JWT_SECRET=$(New-Secret 48)" }
        '^HTTP_PORT=' { "HTTP_PORT=$HttpPort" }
        '^HTTPS_PORT=' { "HTTPS_PORT=$HttpsPort" }
        default { $line }
    }
}
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllLines($target, [string[]]$lines, $utf8NoBom)
Write-Host "Створено $target (секрети не виводяться й не потрапляють у git)."
