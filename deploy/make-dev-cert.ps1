<#
.SYNOPSIS
  Самопідписаний TLS-сертифікат для локального розгортання (Nginx).
.DESCRIPTION
  Створює deploy/certs/server.crt і server.key (RSA 2048, 365 днів) за
  допомогою openssl у тимчасовому контейнері, тому окремо встановлювати
  openssl не потрібно. Ключі в git не потрапляють (.gitignore).
.EXAMPLE
  .\deploy\make-dev-cert.ps1          # localhost, bore.pub (тунель для вузла)
  .\deploy\make-dev-cert.ps1 -Names localhost, oberih.local
#>
param([string[]]$Names = @("localhost", "bore.pub"))
$ErrorActionPreference = "Stop"

$certs = Join-Path $PSScriptRoot "certs"
New-Item -ItemType Directory -Force $certs | Out-Null
$san = (@($Names | ForEach-Object { "DNS:$_" }) + "IP:127.0.0.1") -join ","
$openssl = "apk add --no-cache openssl >/dev/null && " +
    "openssl req -x509 -newkey rsa:2048 -nodes -days 365 " +
    "-subj '/CN=$($Names[0])' -addext 'subjectAltName=$san' " +
    "-keyout /certs/server.key -out /certs/server.crt && " +
    "chmod 644 /certs/server.crt /certs/server.key"
docker run --rm -v "${certs}:/certs" alpine:3.20 sh -c $openssl
if ($LASTEXITCODE -ne 0) {
    Write-Host "Не вдалося створити сертифікат (чи запущено Docker?)."
    exit 1
}
Write-Host "Сертифікат: $certs\server.crt ($san)"
