<#
.SYNOPSIS
  Перевірка розгорнутої системи «Оберіг» (smoke-тест, ЛБ5).
.DESCRIPTION
  Перевіряє: здоров'я й БД, вхід демо-користувача, постановку, подію вузла,
  дублікат, зняття, команди вузлу в heartbeat, потік запитів вузла без 429,
  резервну копію, обмеження частоти входу. Створює тимчасовий об'єкт із
  вузлом і в кінці видаляє його, тож демо-дані не змінюються.
  Завершується з кодом 1 при першому збої.
.EXAMPLE
  .\deploy\smoke-test.ps1 -BaseUrl https://localhost -Password Demo-Password-1 -SkipCertificateCheck
#>
param(
    [string]$BaseUrl = "https://localhost",
    [Parameter(Mandatory = $true)][string]$Password,
    [string]$OwnerEmail = "owner@oberih.local",
    [string]$AdminEmail = "admin@oberih.local",
    [switch]$SkipCertificateCheck,
    [switch]$SkipRateLimitCheck
)
$ErrorActionPreference = "Stop"
$Api = "$($BaseUrl.TrimEnd('/'))/api/v1"
$script:Extra = @{}
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

if ($SkipCertificateCheck) {
    if ($PSVersionTable.PSVersion.Major -ge 6) {
        $script:Extra = @{ SkipCertificateCheck = $true }
    } else {
        # Windows PowerShell 5.1 не має -SkipCertificateCheck.
        Add-Type @"
using System.Net; using System.Security.Cryptography.X509Certificates;
public class OberihTrustAll : ICertificatePolicy {
    public bool CheckValidationResult(ServicePoint s, X509Certificate c,
        WebRequest r, int p) { return true; }
}
"@
        [Net.ServicePointManager]::CertificatePolicy = New-Object OberihTrustAll
    }
}

function Invoke-Api($Method, $Path, $Body = $null, $Headers = @{}) {
    $request = @{
        Method = $Method; Uri = "$Api$Path"; Headers = $Headers
        ContentType = "application/json; charset=utf-8"; UseBasicParsing = $true
    } + $script:Extra
    if ($null -ne $Body) {
        $request.Body = [Text.Encoding]::UTF8.GetBytes(($Body | ConvertTo-Json -Depth 10))
    }
    try {
        $response = Invoke-WebRequest @request
        $json = $null
        if ($response.Content) { $json = $response.Content | ConvertFrom-Json }
        return [pscustomobject]@{ Status = [int]$response.StatusCode; Body = $json }
    } catch {
        $raw = $_.Exception.Response
        if ($null -eq $raw) { throw }
        return [pscustomobject]@{ Status = [int]$raw.StatusCode; Body = $null }
    }
}

$script:Step = 0
function Assert-That([bool]$Condition, [string]$Message) {
    $script:Step++
    if (-not $Condition) {
        Write-Host ("[{0:00}] FAIL  {1}" -f $script:Step, $Message) -ForegroundColor Red
        exit 1
    }
    Write-Host ("[{0:00}] ok    {1}" -f $script:Step, $Message) -ForegroundColor Green
}

function Get-AuthHeader($Email) {
    $login = Invoke-Api POST "/auth/login" @{ email = $Email; password = $Password }
    Assert-That ($login.Status -eq 200) "вхід $Email"
    @{ Authorization = "Bearer $($login.Body.access_token)" }
}

function Now([int]$Seconds = 0) {
    (Get-Date).ToUniversalTime().AddSeconds($Seconds).ToString("o")
}

# 1. Здоров'я сервісу й БД
$health = Invoke-Api GET "/health"
Assert-That ($health.Status -eq 200 -and $health.Body.database -eq "ok") "health: сервіс і БД"

# 2. Вхід демо-користувачів
$Owner = Get-AuthHeader $OwnerEmail
$Admin = Get-AuthHeader $AdminEmail
$Confirm = @{ confirmation = @{ method = "password"; value = $Password } }

# 3. Тимчасовий об'єкт із зоною, вузлом і герконом
$stamp = Get-Date -Format "yyyyMMddHHmmss"
$facility = Invoke-Api POST "/facilities" @{ name = "Smoke $stamp" } $Owner
Assert-That ($facility.Status -eq 201) "створення тимчасового об'єкта"
$FID = $facility.Body.id
try {
    $zone = Invoke-Api POST "/facilities/$FID/zones" @{ name = "Двері"; zone_type = "perimeter" } $Owner
    $node = Invoke-Api POST "/facilities/$FID/nodes" @{ name = "Smoke"; serial = "SMOKE-$stamp" } $Owner
    $sensor = Invoke-Api POST "/facilities/$FID/nodes/$($node.Body.id)/sensors" @{
        zone_id = $zone.Body.id; name = "Геркон"; sensor_type = "reed"; channel = 1 } $Owner
    $commission = Invoke-Api POST "/facilities/$FID/nodes/$($node.Body.id)/commission" $null $Owner
    Assert-That ($sensor.Status -eq 201 -and $commission.Body.command_key.Length -eq 64) `
        "вузол, датчик, введення в експлуатацію (токен і ключ)"
    $Device = @{ "X-Device-Token" = $commission.Body.device_token }

    # 4. Постановка в режим «Вдома»
    $arm = Invoke-Api POST "/facilities/$FID/arm" @{ mode = "home" } $Owner
    Assert-That ($arm.Body.mode -eq "armed_home") "постановка: armed_home"

    # 5. Подія вузла й дублікат
    $batch = @{ events = @(@{ channel = 1; event_type = "opened"; seq = 1; occurred_at = (Now) }) }
    $first = Invoke-Api POST "/device/events" $batch $Device
    Assert-That ($first.Body.accepted -eq 1) "подія геркона прийнята"
    $mode = (Invoke-Api GET "/facilities/$FID" $null $Owner).Body.mode
    Assert-That ($mode -eq "entry_delay") "автомат: entry_delay після спрацювання"
    $again = Invoke-Api POST "/device/events" $batch $Device
    Assert-That ($again.Body.duplicates -eq 1) "повторне надсилання — дублікат"

    # 6. Зняття з охорони з підтвердженням
    $disarm = Invoke-Api POST "/facilities/$FID/disarm" $Confirm $Owner
    Assert-That ($disarm.Body.mode -eq "disarmed") "зняття з охорони"

    # 7. Команди вузлу: arm_home і disarm у heartbeat
    $beat = Invoke-Api POST "/device/heartbeat" @{ firmware_version = "smoke" } $Device
    $types = @($beat.Body.commands | ForEach-Object { $_.type }) -join ","
    Assert-That ($types -eq "arm_home,disarm") "heartbeat: підписані команди ($types)"

    # 8. Потік вузла (буфер після відновлення зв'язку) не впирається в 429
    $codes = 1..10 | ForEach-Object {
        (Invoke-Api POST "/device/heartbeat" @{} $Device).Status
    }
    Assert-That (-not ($codes -contains 429)) "10 запитів вузла поспіль без 429"

    # 9. Резервна копія
    $backup = Invoke-Api POST "/admin/backups" @{ kind = "settings" } $Admin
    Assert-That ($backup.Status -eq 201 -and $backup.Body.status -eq "completed") `
        "резервна копія налаштувань ($($backup.Body.size_bytes) байт)"
} finally {
    $deleted = Invoke-Api DELETE "/facilities/$FID" $null $Owner
    Write-Host "Тимчасовий об'єкт видалено (HTTP $($deleted.Status))."
}

# 10. Обмеження частоти входу (останнім: вичерпує ліміт на хвилину)
if (-not $SkipRateLimitCheck) {
    $codes = 1..20 | ForEach-Object {
        (Invoke-Api POST "/auth/login" @{ email = "nobody@oberih.local"; password = "x" }).Status
    }
    Assert-That ($codes -contains 429) "обмеження частоти /auth: 429 після серії входів"
}

Write-Host "Smoke-тест пройдено." -ForegroundColor Green
exit 0
