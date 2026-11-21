// Формат обміну з сервером (JSON): пакет подій, heartbeat, команди.
// Контракт — server/app/schemas/events.py (DeviceEventBatch, HeartbeatIn,
// HeartbeatOut, NodeCommandOut).
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include "command_verifier.h"
#include "domain.h"
#include "event_buffer.h"
#include "settings.h"

// Що вузол повідомляє серверу в heartbeat.
struct HeartbeatReport {
  const char* firmware_version;
  Mode mode;
  uint32_t config_version;
  size_t buffer_depth;
  std::vector<std::string> acked_command_ids;
};

// Відповідь сервера на heartbeat.
struct HeartbeatReply {
  int64_t server_epoch = 0;
  uint32_t poll_interval_s = 0;
  std::string facility_mode;
  uint64_t last_seq = 0;
  bool has_config = false;
  NodeSettings config{};  // лише числові поля й config_version
  std::vector<Command> commands;
};

// Секунди Unix -> "YYYY-MM-DDTHH:MM:SSZ".
std::string format_utc(int64_t epoch_s);

std::string build_events_json(const BufferedEvent* events, size_t count);
std::string build_heartbeat_json(const HeartbeatReport& report);

bool parse_heartbeat(const std::string& body, HeartbeatReply* out);
// Відповідь на пакет подій: скільки прийнято нових і скільки дублікатів.
bool parse_events_result(const std::string& body, uint32_t* accepted,
                         uint32_t* duplicates);
// payload команди arm/disarm: {"mode": "..."}.
bool parse_mode_payload(const std::string& payload, std::string* mode);
// payload команди set_config: повна конфігурація вузла.
bool parse_config_payload(const std::string& payload, NodeSettings* out);
