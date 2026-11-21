// Налаштування вузла (ІК-8): значення, перевірка меж, збереження в NVS.
// Змінюються з консолі Serial або конфігурацією з сервера (за зростанням
// config_version). BLE у Wokwi не емулюється (ЗЛ-1), тому консоль його заміняє.
#pragma once

#include <cstdint>
#include <string>

#include "config.h"
#include "storage.h"

struct NodeSettings {
  uint32_t exit_delay_s;
  uint32_t entry_delay_s;
  uint32_t poll_interval_s;
  uint32_t debounce_ms;
  uint32_t pir_lockout_s;
  uint32_t config_version;  // 0 — конфігурацію з сервера ще не отримано
  char server_url[config::kServerUrlCapacity];
};

enum class SettingResult : uint8_t {
  kOk,
  kUnknownKey,
  kInvalidNumber,
  kOutOfRange,
  kInvalidUrl,
};

enum class ConfigApplyResult : uint8_t { kApplied, kStale, kInvalid };

const char* setting_result_message(SettingResult result);

NodeSettings default_settings();

// Змінює одне значення за назвою; невалідне значення не змінює налаштувань.
SettingResult set_setting(NodeSettings& settings, const std::string& key,
                          const std::string& value);

// Перевіряє межі всіх числових значень.
bool settings_valid(const NodeSettings& settings);

// Конфігурація з сервера: застосовується повністю, лише якщо версія більша
// за чинну й усі значення в межах. server_url не змінюється.
ConfigApplyResult apply_server_config(NodeSettings& settings,
                                      const NodeSettings& incoming);

// Текст для консольної команди get.
std::string describe_settings(const NodeSettings& settings);

bool load_settings(KeyValueStore& store, NodeSettings* out);
bool save_settings(KeyValueStore& store, const NodeSettings& settings);
