// Усі константи вузла: піни, канали, значення за замовчуванням і межі.
// Значення за замовчуванням збігаються з Vision & Scope і сервером.
#pragma once

#include <cstddef>
#include <cstdint>

namespace config {

constexpr const char* kFirmwareVersion = "0.4.0";
constexpr uint32_t kSerialBaud = 115200;

// --- Wi-Fi (симуляція Wokwi: відкрита мережа, канал 6) ----------------------
constexpr const char* kWifiSsid = "Wokwi-GUEST";
constexpr const char* kWifiPassword = "";
constexpr int32_t kWifiChannel = 6;
constexpr uint32_t kWifiRetryMs = 5000;

// --- Піни ESP32 DevKit C v4 --------------------------------------------------
constexpr uint8_t kPinDoorReed = 13;    // канал 1, перемикач на GND
constexpr uint8_t kPinWindowReed = 14;  // канал 2, перемикач на GND
constexpr uint8_t kPinPir = 27;         // канал 3, вихід HIGH під час руху
constexpr uint8_t kPinTamper = 26;      // канал 4, перемикач на GND
constexpr uint8_t kPinLedRed = 25;
constexpr uint8_t kPinLedGreen = 33;
constexpr uint8_t kPinLedBlue = 32;
constexpr uint8_t kPinBuzzer = 23;
constexpr uint8_t kBuzzerPwmChannel = 0;

// --- Канали (збігаються з демо-даними сервера, seed.py) ----------------------
constexpr uint8_t kChannelDoor = 1;
constexpr uint8_t kChannelWindow = 2;
constexpr uint8_t kChannelPir = 3;
constexpr uint8_t kChannelTamper = 4;

// --- Налаштування за замовчуванням (ІК-2, ІК-3, ІК-8) ------------------------
constexpr uint32_t kDefaultExitDelayS = 30;
constexpr uint32_t kDefaultEntryDelayS = 30;
constexpr uint32_t kDefaultPollIntervalS = 30;
constexpr uint32_t kDefaultDebounceMs = 50;
constexpr uint32_t kDefaultPirLockoutS = 10;

// Межі значень (такі самі перевіряє сервер, schemas/facilities.py).
constexpr uint32_t kMinDelayS = 0;
constexpr uint32_t kMaxDelayS = 600;
constexpr uint32_t kMinPollIntervalS = 5;
constexpr uint32_t kMaxPollIntervalS = 3600;
constexpr uint32_t kMinDebounceMs = 10;
constexpr uint32_t kMaxDebounceMs = 1000;
constexpr uint32_t kMinPirLockoutS = 0;
constexpr uint32_t kMaxPirLockoutS = 600;
constexpr size_t kServerUrlCapacity = 128;

// --- Буфер подій (ІК-4) ------------------------------------------------------
constexpr size_t kEventBufferCapacity = 64;
constexpr size_t kMaxBatchSize = 20;  // сервер приймає до 200 подій у пакеті

// --- Повтори (ІК-5) ----------------------------------------------------------
constexpr uint32_t kBackoffBaseMs = 1000;
constexpr uint32_t kBackoffMaxMs = 60000;
constexpr uint32_t kBackoffJitterMaxMs = 250;
// Скільки разів повторювати пакет, який сервер відхилив як некоректний (4xx).
constexpr uint32_t kMaxRejectedAttempts = 3;
constexpr uint32_t kHttpTimeoutMs = 8000;

// --- Зв'язок і індикація (ІК-6) ----------------------------------------------
constexpr uint32_t kMissedPollsLimit = 3;  // N(проп.) з Vision & Scope
constexpr uint32_t kRestoredIndicationMs = 3000;
constexpr uint32_t kOfflineBlinkPeriodMs = 1000;
constexpr uint32_t kOfflineBeepPeriodMs = 10000;
constexpr uint32_t kOfflineBeepMs = 200;
constexpr uint32_t kDelayBlinkPeriodMs = 500;
constexpr uint32_t kAlarmBlinkPeriodMs = 200;
constexpr uint16_t kAlarmToneHz = 2000;
constexpr uint16_t kNoticeToneHz = 1000;

// --- Команди сервера (ІК-7) --------------------------------------------------
constexpr int64_t kCommandMaxSkewS = 60;
constexpr size_t kCommandKeyBytes = 32;
constexpr size_t kMaxPendingAcks = 16;

// --- Симуляція брязкоту (Wokwi його не моделює) ------------------------------
constexpr uint32_t kSimBounceToggles = 9;
constexpr uint32_t kSimBounceIntervalMs = 5;

}  // namespace config
