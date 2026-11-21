#include "settings.h"

#include <cstdlib>
#include <cstring>

#if __has_include("secrets.h")
#include "secrets.h"
#endif
#ifndef OBERIH_SERVER_URL
#define OBERIH_SERVER_URL ""
#endif

namespace {

constexpr const char* kKeySettings = "settings";
constexpr uint32_t kFormatMagic = 0x4F425331;  // "OBS1"
constexpr const char* kHttpsPrefix = "https://";

struct StoredSettings {
  uint32_t magic;
  NodeSettings settings;
};

// Опис числового параметра: назва в консолі, поле й межі.
struct NumericField {
  const char* key;
  uint32_t NodeSettings::*field;
  uint32_t min_value;
  uint32_t max_value;
};

constexpr NumericField kNumericFields[] = {
    {"exit_delay", &NodeSettings::exit_delay_s, config::kMinDelayS,
     config::kMaxDelayS},
    {"entry_delay", &NodeSettings::entry_delay_s, config::kMinDelayS,
     config::kMaxDelayS},
    {"poll_interval", &NodeSettings::poll_interval_s, config::kMinPollIntervalS,
     config::kMaxPollIntervalS},
    {"debounce_ms", &NodeSettings::debounce_ms, config::kMinDebounceMs,
     config::kMaxDebounceMs},
    {"pir_lockout", &NodeSettings::pir_lockout_s, config::kMinPirLockoutS,
     config::kMaxPirLockoutS},
};

bool parse_uint(const std::string& text, uint32_t* out) {
  if (text.empty() || text.size() > 9) {
    return false;
  }
  for (char symbol : text) {
    if (symbol < '0' || symbol > '9') {
      return false;
    }
  }
  *out = static_cast<uint32_t>(std::strtoul(text.c_str(), nullptr, 10));
  return true;
}

bool in_range(const NumericField& field, uint32_t value) {
  return value >= field.min_value && value <= field.max_value;
}

SettingResult set_server_url(NodeSettings& settings, const std::string& value) {
  const bool https = value.rfind(kHttpsPrefix, 0) == 0;
  if (!https || value.size() >= sizeof(settings.server_url)) {
    return SettingResult::kInvalidUrl;
  }
  std::strncpy(settings.server_url, value.c_str(), sizeof(settings.server_url));
  settings.server_url[sizeof(settings.server_url) - 1] = '\0';
  return SettingResult::kOk;
}

}  // namespace

const char* setting_result_message(SettingResult result) {
  switch (result) {
    case SettingResult::kOk:
      return "ok";
    case SettingResult::kUnknownKey:
      return "unknown setting";
    case SettingResult::kInvalidNumber:
      return "value must be a non-negative integer";
    case SettingResult::kOutOfRange:
      return "value is out of range";
    case SettingResult::kInvalidUrl:
      return "server_url must start with https:// and be shorter than 128";
  }
  return "unknown error";
}

NodeSettings default_settings() {
  NodeSettings settings{};
  settings.exit_delay_s = config::kDefaultExitDelayS;
  settings.entry_delay_s = config::kDefaultEntryDelayS;
  settings.poll_interval_s = config::kDefaultPollIntervalS;
  settings.debounce_ms = config::kDefaultDebounceMs;
  settings.pir_lockout_s = config::kDefaultPirLockoutS;
  settings.config_version = 0;
  std::strncpy(settings.server_url, OBERIH_SERVER_URL,
               sizeof(settings.server_url) - 1);
  return settings;
}

SettingResult set_setting(NodeSettings& settings, const std::string& key,
                          const std::string& value) {
  if (key == "server_url") {
    return set_server_url(settings, value);
  }
  for (const NumericField& field : kNumericFields) {
    if (key != field.key) {
      continue;
    }
    uint32_t number = 0;
    if (!parse_uint(value, &number)) {
      return SettingResult::kInvalidNumber;
    }
    if (!in_range(field, number)) {
      return SettingResult::kOutOfRange;
    }
    settings.*field.field = number;
    return SettingResult::kOk;
  }
  return SettingResult::kUnknownKey;
}

bool settings_valid(const NodeSettings& settings) {
  for (const NumericField& field : kNumericFields) {
    if (!in_range(field, settings.*field.field)) {
      return false;
    }
  }
  return true;
}

ConfigApplyResult apply_server_config(NodeSettings& settings,
                                      const NodeSettings& incoming) {
  if (incoming.config_version <= settings.config_version) {
    return ConfigApplyResult::kStale;
  }
  if (!settings_valid(incoming)) {
    return ConfigApplyResult::kInvalid;
  }
  for (const NumericField& field : kNumericFields) {
    settings.*field.field = incoming.*field.field;
  }
  settings.config_version = incoming.config_version;
  return ConfigApplyResult::kApplied;
}

std::string describe_settings(const NodeSettings& settings) {
  std::string text;
  for (const NumericField& field : kNumericFields) {
    text += std::string(field.key) + " = " +
            std::to_string(settings.*field.field) + "  [" +
            std::to_string(field.min_value) + ".." +
            std::to_string(field.max_value) + "]\n";
  }
  text += "config_version = " + std::to_string(settings.config_version) + "\n";
  text += "server_url = " + std::string(settings.server_url) + "\n";
  return text;
}

bool load_settings(KeyValueStore& store, NodeSettings* out) {
  StoredSettings stored{};
  if (!store.read_blob(kKeySettings, &stored, sizeof(stored)) ||
      stored.magic != kFormatMagic || !settings_valid(stored.settings)) {
    return false;
  }
  stored.settings.server_url[sizeof(stored.settings.server_url) - 1] = '\0';
  *out = stored.settings;
  return true;
}

bool save_settings(KeyValueStore& store, const NodeSettings& settings) {
  StoredSettings stored{};
  stored.magic = kFormatMagic;
  stored.settings = settings;
  return store.write_blob(kKeySettings, &stored, sizeof(stored));
}
