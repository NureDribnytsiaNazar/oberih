#include "protocol.h"

#include <ArduinoJson.h>

#include <cstdio>

namespace {

constexpr int64_t kSecondsPerDay = 86400;
constexpr int64_t kSecondsPerHour = 3600;
constexpr int64_t kSecondsPerMinute = 60;

// Дата за кількістю днів від 1970-01-01 (алгоритм civil_from_days,
// H. Hinnant) — без gmtime(), однаково на ESP32 і ПК.
void civil_from_days(int64_t days, int64_t* year, unsigned* month,
                     unsigned* day) {
  days += 719468;
  const int64_t era = (days >= 0 ? days : days - 146096) / 146097;
  const unsigned day_of_era = static_cast<unsigned>(days - era * 146097);
  const unsigned year_of_era =
      (day_of_era - day_of_era / 1460 + day_of_era / 36524 -
       day_of_era / 146096) / 365;
  const unsigned day_of_year =
      day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
  const unsigned month_index = (5 * day_of_year + 2) / 153;
  *day = day_of_year - (153 * month_index + 2) / 5 + 1;
  *month = month_index < 10 ? month_index + 3 : month_index - 9;
  *year = static_cast<int64_t>(year_of_era) + era * 400 + (*month <= 2 ? 1 : 0);
}

// Числове поле конфігурації: false, якщо його немає або тип інший.
bool read_uint(JsonVariantConst value, uint32_t* out) {
  if (!value.is<uint32_t>()) {
    return false;
  }
  *out = value.as<uint32_t>();
  return true;
}

bool read_config(JsonObjectConst object, NodeSettings* out) {
  return read_uint(object["exit_delay_s"], &out->exit_delay_s) &&
         read_uint(object["entry_delay_s"], &out->entry_delay_s) &&
         read_uint(object["poll_interval_s"], &out->poll_interval_s) &&
         read_uint(object["debounce_ms"], &out->debounce_ms) &&
         read_uint(object["pir_lockout_s"], &out->pir_lockout_s) &&
         read_uint(object["config_version"], &out->config_version);
}

bool read_command(JsonObjectConst object, Command* out) {
  if (!object["id"].is<const char*>() || !object["type"].is<const char*>() ||
      !object["payload"].is<const char*>() ||
      !object["signature"].is<const char*>() ||
      !object["nonce"].is<uint64_t>() || !object["issued_at"].is<int64_t>()) {
    return false;
  }
  out->id = object["id"].as<const char*>();
  out->type = object["type"].as<const char*>();
  out->payload = object["payload"].as<const char*>();
  out->signature = object["signature"].as<const char*>();
  out->nonce = object["nonce"].as<uint64_t>();
  out->issued_at = object["issued_at"].as<int64_t>();
  return true;
}

}  // namespace

std::string format_utc(int64_t epoch_s) {
  int64_t days = epoch_s / kSecondsPerDay;
  int64_t seconds = epoch_s % kSecondsPerDay;
  if (seconds < 0) {
    seconds += kSecondsPerDay;
    --days;
  }
  int64_t year = 0;
  unsigned month = 0;
  unsigned day = 0;
  civil_from_days(days, &year, &month, &day);
  char text[32];
  std::snprintf(text, sizeof(text), "%04lld-%02u-%02uT%02u:%02u:%02uZ",
                static_cast<long long>(year), month, day,
                static_cast<unsigned>(seconds / kSecondsPerHour),
                static_cast<unsigned>(seconds % kSecondsPerHour /
                                      kSecondsPerMinute),
                static_cast<unsigned>(seconds % kSecondsPerMinute));
  return text;
}

std::string build_events_json(const BufferedEvent* events, size_t count) {
  JsonDocument doc;
  JsonArray items = doc["events"].to<JsonArray>();
  for (size_t i = 0; i < count; ++i) {
    const BufferedEvent& event = events[i];
    JsonObject item = items.add<JsonObject>();
    item["channel"] = event.channel;
    item["event_type"] = event_type_name(event.type);
    item["seq"] = event.seq;
    item["occurred_at"] = format_utc(event.epoch_s);
    if (event.flags & EventBuffer::kFlagApproxTime) {
      item["payload"]["approx_time"] = true;
    }
  }
  std::string body;
  serializeJson(doc, body);
  return body;
}

std::string build_heartbeat_json(const HeartbeatReport& report) {
  JsonDocument doc;
  doc["firmware_version"] = report.firmware_version;
  doc["mode"] = mode_name(report.mode);
  doc["config_version"] = report.config_version;
  doc["buffer_depth"] = report.buffer_depth;
  JsonArray acks = doc["acked_command_ids"].to<JsonArray>();
  for (const std::string& id : report.acked_command_ids) {
    acks.add(id);
  }
  std::string body;
  serializeJson(doc, body);
  return body;
}

bool parse_heartbeat(const std::string& body, HeartbeatReply* out) {
  JsonDocument doc;
  if (deserializeJson(doc, body) != DeserializationError::Ok) {
    return false;
  }
  if (!doc["server_epoch"].is<int64_t>() ||
      !doc["facility_mode"].is<const char*>()) {
    return false;
  }
  out->server_epoch = doc["server_epoch"].as<int64_t>();
  out->poll_interval_s = doc["poll_interval_s"].as<uint32_t>();
  out->facility_mode = doc["facility_mode"].as<const char*>();
  out->last_seq = doc["last_seq"].as<uint64_t>();
  out->has_config = doc["config"].is<JsonObjectConst>() &&
                    read_config(doc["config"].as<JsonObjectConst>(),
                                &out->config);
  out->commands.clear();
  for (JsonObjectConst item : doc["commands"].as<JsonArrayConst>()) {
    Command command;
    if (read_command(item, &command)) {
      out->commands.push_back(command);
    }
  }
  return true;
}

bool parse_events_result(const std::string& body, uint32_t* accepted,
                         uint32_t* duplicates) {
  JsonDocument doc;
  if (deserializeJson(doc, body) != DeserializationError::Ok) {
    return false;
  }
  return read_uint(doc["accepted"], accepted) &&
         read_uint(doc["duplicates"], duplicates);
}

bool parse_mode_payload(const std::string& payload, std::string* mode) {
  JsonDocument doc;
  if (deserializeJson(doc, payload) != DeserializationError::Ok ||
      !doc["mode"].is<const char*>()) {
    return false;
  }
  *mode = doc["mode"].as<const char*>();
  return true;
}

bool parse_config_payload(const std::string& payload, NodeSettings* out) {
  JsonDocument doc;
  if (deserializeJson(doc, payload) != DeserializationError::Ok) {
    return false;
  }
  return read_config(doc.as<JsonObjectConst>(), out);
}
