#include "node_app.h"

#include <Arduino.h>
#include <WiFi.h>

#include <cinttypes>

#include "config.h"
#include "sha256.h"

#if __has_include("secrets.h")
#include "secrets.h"
#endif
#ifndef OBERIH_NODE_ID
#define OBERIH_NODE_ID ""
#endif
#ifndef OBERIH_DEVICE_TOKEN
#define OBERIH_DEVICE_TOKEN ""
#endif
#ifndef OBERIH_COMMAND_KEY
#define OBERIH_COMMAND_KEY ""
#endif

namespace {

constexpr const char* kNvsNamespace = "oberih";
constexpr const char* kKeyNonce = "nonce";
constexpr const char* kPathHeartbeat = "/api/v1/device/heartbeat";
constexpr const char* kPathEvents = "/api/v1/device/events";
constexpr uint32_t kMsPerSecond = 1000;
constexpr size_t kConsoleLineMax = 160;
constexpr uint32_t kBackoffSeedEvents = 0x0BE21C;
constexpr uint32_t kBackoffSeedHeartbeat = 0x0BE21D;

void log_line(const char* tag, const std::string& message) {
  Serial.printf("[%s] %s\n", tag, message.c_str());
}

}  // namespace

NodeApp::NodeApp()
    : settings_(default_settings()),
      buffer_(store_),
      console_(settings_, *this),
      heartbeat_backoff_(config::kBackoffBaseMs, config::kBackoffMaxMs,
                         config::kBackoffJitterMaxMs, kBackoffSeedHeartbeat),
      events_backoff_(config::kBackoffBaseMs, config::kBackoffMaxMs,
                      config::kBackoffJitterMaxMs, kBackoffSeedEvents),
      contacts_{
          {{config::kChannelDoor, SensorKind::kReed, ZoneKind::kPerimeter},
           config::kPinDoorReed, EventType::kOpened, EventType::kClosed,
           Debouncer(false, config::kDefaultDebounceMs)},
          {{config::kChannelWindow, SensorKind::kReed, ZoneKind::kPerimeter},
           config::kPinWindowReed, EventType::kOpened, EventType::kClosed,
           Debouncer(false, config::kDefaultDebounceMs)},
          {{config::kChannelTamper, SensorKind::kTamper, ZoneKind::kAlwaysOn},
           config::kPinTamper, EventType::kTamper, EventType::kTamperRestored,
           Debouncer(false, config::kDefaultDebounceMs)},
      },
      pir_info_{config::kChannelPir, SensorKind::kPir, ZoneKind::kInterior},
      pir_lockout_(config::kDefaultPirLockoutS),
      node_id_(OBERIH_NODE_ID) {}

// --- Запуск ------------------------------------------------------------------

void NodeApp::begin() {
  Serial.begin(config::kSerialBaud);
  Serial.printf("\nOberih node %s\n", config::kFirmwareVersion);

  for (ContactInput& contact : contacts_) {
    pinMode(contact.pin, INPUT_PULLUP);
    // Розімкнений контакт підтягнутий до HIGH: двері відчинено / корпус знято.
    contact.filter = Debouncer(digitalRead(contact.pin) == HIGH,
                               settings_.debounce_ms);
  }
  pinMode(config::kPinPir, INPUT);
  pinMode(config::kPinLedRed, OUTPUT);
  pinMode(config::kPinLedGreen, OUTPUT);
  pinMode(config::kPinLedBlue, OUTPUT);
  ledcSetup(config::kBuzzerPwmChannel, config::kNoticeToneHz, 8);
  ledcAttachPin(config::kPinBuzzer, config::kBuzzerPwmChannel);

  load_state();
  load_command_key();
  net_.begin(OBERIH_DEVICE_TOKEN);
  net_.set_server_url(settings_.server_url);
  if (!net_.tls_ready()) {
    log_line("net", "no root CA (secrets.h) and no OBERIH_DEV_TLS: offline");
  }
  WiFi.mode(WIFI_STA);
  WiFi.begin(config::kWifiSsid, config::kWifiPassword, config::kWifiChannel);
  log_line("node", "ready, type help for console commands");
}

void NodeApp::load_state() {
  if (!store_.begin(kNvsNamespace)) {
    log_line("nvs", "NVS unavailable, using defaults");
  }
  NodeSettings stored{};
  if (load_settings(store_, &stored)) {
    settings_ = stored;
    log_line("nvs", "settings loaded");
  }
  settings_changed();
  buffer_.load();
  if (!store_.read_u64(kKeyNonce, &last_nonce_)) {
    last_nonce_ = 0;
  }
  log_line("nvs", "buffer " + std::to_string(buffer_.size()) + " events, seq " +
                      std::to_string(buffer_.last_seq()));
}

void NodeApp::load_command_key() {
  commands_enabled_ = !node_id_.empty() &&
                      from_hex(OBERIH_COMMAND_KEY, command_key_,
                               sizeof(command_key_));
  if (!commands_enabled_) {
    log_line("cmd", "no node id or command key: server commands disabled");
  }
}

Delays NodeApp::delays() const {
  return {settings_.exit_delay_s, settings_.entry_delay_s};
}

// --- Головний цикл -------------------------------------------------------------

void NodeApp::loop() {
  const uint32_t now_ms = millis();
  poll_console();
  poll_contacts(now_ms);
  poll_pir(now_ms);
  if (machine_.tick(delays(), now_ms)) {
    log_line("mode", std::string("timer -> ") + mode_name(machine_.mode()));
  }
  service_wifi(now_ms);
  service_events(now_ms);
  service_heartbeat(now_ms);
  update_indicators(now_ms);
}

void NodeApp::poll_console() {
  while (Serial.available() > 0) {
    const char symbol = static_cast<char>(Serial.read());
    if (symbol == '\r') {
      continue;
    }
    if (symbol != '\n') {
      if (console_line_.size() < kConsoleLineMax) {
        console_line_.push_back(symbol);
      }
      continue;
    }
    Serial.printf("> %s\n", console_line_.c_str());
    Serial.print(console_.handle_line(console_line_).c_str());
    console_line_.clear();
  }
}

// --- Датчики -------------------------------------------------------------------

void NodeApp::poll_contacts(uint32_t now_ms) {
  for (ContactInput& contact : contacts_) {
    const bool raw_open = digitalRead(contact.pin) == HIGH;
    if (contact.filter.feed(raw_open, now_ms) != DebounceResult::kChanged) {
      continue;
    }
    const EventType type = contact.filter.stable() ? contact.active_event
                                                   : contact.inactive_event;
    record_event(contact.info, type, now_ms);
  }
}

void NodeApp::poll_pir(uint32_t now_ms) {
  const bool level = digitalRead(config::kPinPir) == HIGH;
  const bool rising = level && !pir_level_;
  pir_level_ = level;
  if (!rising) {
    return;
  }
  if (!pir_lockout_.accept(now_ms)) {
    log_line("pir", "motion ignored (lockout " +
                        std::to_string(settings_.pir_lockout_s) + " s)");
    return;
  }
  record_event(pir_info_, EventType::kMotion, now_ms);
}

void NodeApp::record_event(const ChannelInfo& info, EventType type,
                           uint32_t now_ms) {
  bool alarm = false;
  if (is_trigger_event(type)) {
    const bool changed =
        machine_.on_sensor_trigger(info.sensor, info.zone, delays(), now_ms);
    alarm = changed || info.sensor == SensorKind::kTamper;
  }
  const uint64_t seq = buffer_.push(info.channel, type, alarm, clock_, now_ms);
  Serial.printf("[event] seq=%" PRIu64 " ch=%u %s mode=%s%s\n", seq,
                info.channel, event_type_name(type), mode_name(machine_.mode()),
                alarm ? " ALARM" : "");
  if (events_backoff_.attempts() == 0) {
    next_events_ms_ = now_ms;  // надіслати одразу, якщо немає повторів
  }
}

// --- Мережа --------------------------------------------------------------------

void NodeApp::service_wifi(uint32_t now_ms) {
  const bool connected = WiFi.status() == WL_CONNECTED;
  if (connected != wifi_was_connected_) {
    wifi_was_connected_ = connected;
    log_line("wifi", connected ? "connected" : "disconnected");
  }
  if (connected || !network_enabled_ ||
      static_cast<int32_t>(now_ms - next_wifi_attempt_ms_) < 0) {
    return;
  }
  next_wifi_attempt_ms_ = now_ms + config::kWifiRetryMs;
  WiFi.begin(config::kWifiSsid, config::kWifiPassword, config::kWifiChannel);
}

void NodeApp::service_heartbeat(uint32_t now_ms) {
  if (static_cast<int32_t>(now_ms - next_heartbeat_ms_) < 0) {
    return;
  }
  if (!network_enabled_ || WiFi.status() != WL_CONNECTED) {
    heartbeat_failed(-1, now_ms);
    return;
  }
  HeartbeatReport report{config::kFirmwareVersion, machine_.mode(),
                         settings_.config_version, buffer_.size(),
                         pending_acks_};
  const HttpResult result =
      net_.post_json(kPathHeartbeat, build_heartbeat_json(report));
  HeartbeatReply reply;
  if (classify_response(result.status) != SendOutcome::kDelivered ||
      !parse_heartbeat(result.body, &reply)) {
    heartbeat_failed(result.status, millis());
    return;
  }
  // Підтвердження доставлено: прибираємо лише ті, що були в цьому запиті.
  pending_acks_.erase(pending_acks_.begin(),
                      pending_acks_.begin() + report.acked_command_ids.size());
  heartbeat_succeeded(reply, millis());
}

void NodeApp::heartbeat_succeeded(const HeartbeatReply& reply,
                                  uint32_t now_ms) {
  const bool first_sync = !clock_.synced();
  clock_.sync(reply.server_epoch, now_ms);
  if (first_sync) {
    buffer_.resolve_times(clock_);
    log_line("clock", "synced with server: " + format_utc(reply.server_epoch));
  }
  if (buffer_.adopt_server_seq(reply.last_seq)) {
    log_line("buffer", "seq continues after server last_seq " +
                           std::to_string(reply.last_seq));
  }
  if (!online()) {
    restored_ = true;
    restored_at_ms_ = now_ms;
    log_line("net", "connection restored");
  }
  missed_polls_ = 0;
  heartbeat_backoff_.reset();
  next_heartbeat_ms_ = now_ms + settings_.poll_interval_s * kMsPerSecond;
  if (reply.has_config) {
    apply_server_settings(reply.config, "heartbeat");
  }
  for (const Command& command : reply.commands) {
    process_command(command, now_ms);
  }
  if (machine_.mode() != reported_mode_ ||
      reply.facility_mode != mode_name(machine_.mode())) {
    reported_mode_ = machine_.mode();
    log_line("mode", std::string("node ") + mode_name(machine_.mode()) +
                         ", server " + reply.facility_mode);
  }
}

void NodeApp::heartbeat_failed(int status, uint32_t now_ms) {
  ++missed_polls_;
  restored_ = false;
  const uint32_t delay_ms = heartbeat_backoff_.next_delay_ms();
  next_heartbeat_ms_ = now_ms + delay_ms;
  Serial.printf("[net] heartbeat failed (status %d), missed %u, retry in %u ms\n",
                status, static_cast<unsigned>(missed_polls_),
                static_cast<unsigned>(delay_ms));
  if (missed_polls_ == config::kMissedPollsLimit) {
    log_line("net", "server unreachable: offline indication on");
  }
}

void NodeApp::service_events(uint32_t now_ms) {
  if (buffer_.size() == 0 || !clock_.synced() || !network_enabled_ ||
      WiFi.status() != WL_CONNECTED ||
      static_cast<int32_t>(now_ms - next_events_ms_) < 0) {
    return;
  }
  BufferedEvent batch[config::kMaxBatchSize];
  const size_t count = buffer_.peek(batch, config::kMaxBatchSize);
  if (count == 0) {
    return;
  }
  const HttpResult result =
      net_.post_json(kPathEvents, build_events_json(batch, count));
  const uint32_t done_ms = millis();
  switch (classify_response(result.status)) {
    case SendOutcome::kDelivered: {
      uint32_t accepted = 0;
      uint32_t duplicates = 0;
      if (!parse_events_result(result.body, &accepted, &duplicates)) {
        log_line("events", "delivered, response not parsed");
      }
      buffer_.pop(count);
      events_backoff_.reset();
      rejected_attempts_ = 0;
      Serial.printf("[events] sent %u: accepted %u, duplicates %u, left %u\n",
                    static_cast<unsigned>(count), static_cast<unsigned>(accepted),
                    static_cast<unsigned>(duplicates),
                    static_cast<unsigned>(buffer_.size()));
      next_events_ms_ = done_ms;
      return;
    }
    case SendOutcome::kRejected:
      if (++rejected_attempts_ >= config::kMaxRejectedAttempts) {
        Serial.printf("[events] batch rejected (%d) %u times, dropped\n",
                      result.status, static_cast<unsigned>(rejected_attempts_));
        buffer_.pop(count);
        rejected_attempts_ = 0;
        next_events_ms_ = done_ms;
        return;
      }
      break;
    case SendOutcome::kAuthFailed:
      log_line("events", "device token rejected (401/403)");
      next_events_ms_ = done_ms + config::kBackoffMaxMs;
      return;
    case SendOutcome::kRetry:
      break;
  }
  const uint32_t delay_ms = events_backoff_.next_delay_ms();
  next_events_ms_ = done_ms + delay_ms;
  Serial.printf("[events] send failed (status %d), %u buffered, retry in %u ms\n",
                result.status, static_cast<unsigned>(buffer_.size()),
                static_cast<unsigned>(delay_ms));
}

// --- Команди та налаштування сервера ------------------------------------------

void NodeApp::apply_server_settings(const NodeSettings& incoming,
                                    const char* source) {
  switch (apply_server_config(settings_, incoming)) {
    case ConfigApplyResult::kApplied:
      settings_changed();
      if (!::save_settings(store_, settings_)) {
        log_line("nvs", "failed to save settings");
      }
      log_line("config", std::string("applied version ") +
                             std::to_string(settings_.config_version) +
                             " from " + source);
      break;
    case ConfigApplyResult::kInvalid:
      log_line("config", std::string("rejected invalid config from ") + source);
      break;
    case ConfigApplyResult::kStale:
      break;
  }
}

void NodeApp::process_command(const Command& command, uint32_t now_ms) {
  if (pending_acks_.size() < config::kMaxPendingAcks) {
    pending_acks_.push_back(command.id);  // отримання підтверджуємо завжди
  }
  if (!commands_enabled_) {
    log_line("cmd", "ignored " + command.type + ": no command key");
    return;
  }
  const CommandVerifier verifier(command_key_, node_id_);
  const VerifyResult result = verifier.verify(
      command, clock_.synced(), clock_.now(now_ms), last_nonce_);
  if (result != VerifyResult::kAccepted) {
    log_line("cmd", "rejected " + command.type + ": " +
                        verify_result_name(result));
    return;
  }
  last_nonce_ = command.nonce;
  if (!store_.write_u64(kKeyNonce, last_nonce_)) {
    log_line("nvs", "failed to save nonce");
  }
  execute_command(command, now_ms);
}

void NodeApp::execute_command(const Command& command, uint32_t now_ms) {
  if (command.type == "set_config") {
    NodeSettings incoming = settings_;
    if (!parse_config_payload(command.payload, &incoming)) {
      log_line("cmd", "set_config: invalid payload");
      return;
    }
    apply_server_settings(incoming, "command");
    return;
  }
  std::string mode_text;
  Mode target = Mode::kDisarmed;
  if (!parse_mode_payload(command.payload, &mode_text) ||
      !command_target_mode(command.type, mode_text, &target)) {
    log_line("cmd", command.type + ": payload does not match command");
    return;
  }
  machine_.force(target, now_ms);
  log_line("cmd", "executed " + command.type + " -> " + mode_name(target));
}

// --- Індикація -----------------------------------------------------------------

void NodeApp::update_indicators(uint32_t now_ms) {
  const IndicatorInput input{machine_.mode(), !online(), restored_,
                             restored_at_ms_, now_ms};
  const IndicatorOutput out = indicator_state(input);
  digitalWrite(config::kPinLedRed, out.red ? HIGH : LOW);
  digitalWrite(config::kPinLedGreen, out.green ? HIGH : LOW);
  digitalWrite(config::kPinLedBlue, out.blue ? HIGH : LOW);
  if (out.tone_hz != current_tone_hz_) {
    current_tone_hz_ = out.tone_hz;
    ledcWriteTone(config::kBuzzerPwmChannel, out.tone_hz);
  }
}

// --- Консоль (ConsoleActions) -------------------------------------------------

bool NodeApp::save_settings(const NodeSettings& settings) {
  return ::save_settings(store_, settings);
}

void NodeApp::settings_changed() {
  for (ContactInput& contact : contacts_) {
    contact.filter.set_debounce_ms(settings_.debounce_ms);
  }
  pir_lockout_.set_lockout_s(settings_.pir_lockout_s);
  net_.set_server_url(settings_.server_url);
}

std::string NodeApp::status() {
  const uint32_t now_ms = millis();
  std::string text;
  text += std::string("mode: ") + mode_name(machine_.mode()) + "\n";
  text += std::string("network: ") + (network_enabled_ ? "on" : "off") +
          ", wifi " + (WiFi.status() == WL_CONNECTED ? "connected" : "down") +
          ", server " + (online() ? "reachable" : "UNREACHABLE") +
          ", missed polls " + std::to_string(missed_polls_) + "\n";
  text += "clock: " +
          (clock_.synced() ? format_utc(clock_.now(now_ms)) : "not synced") +
          "\n";
  text += "buffer: " + std::to_string(buffer_.size()) + " events, last seq " +
          std::to_string(buffer_.last_seq()) + ", dropped " +
          std::to_string(buffer_.dropped()) + "\n";
  text += "config version: " + std::to_string(settings_.config_version) +
          ", last nonce " + std::to_string(last_nonce_) + "\n";
  text += "storage errors: " + std::to_string(buffer_.storage_errors()) + "\n";
  return text;
}

std::string NodeApp::buffer_dump() {
  std::string text;
  for (size_t i = 0; i < buffer_.size(); ++i) {
    const BufferedEvent& event = buffer_.at(i);
    text += "seq " + std::to_string(event.seq) + " ch " +
            std::to_string(event.channel) + " " + event_type_name(event.type) +
            " " + (event.epoch_s ? format_utc(event.epoch_s) : "time unknown") +
            ((event.flags & EventBuffer::kFlagAlarm) ? " alarm" : "") + "\n";
  }
  return text.empty() ? "buffer is empty\n" : text;
}

void NodeApp::set_network_enabled(bool enabled) {
  network_enabled_ = enabled;
  if (enabled) {
    next_wifi_attempt_ms_ = millis();
    next_heartbeat_ms_ = millis();
  } else {
    WiFi.disconnect();
  }
}

bool NodeApp::simulate_bounce(uint8_t channel) {
  for (ContactInput& contact : contacts_) {
    if (contact.info.channel != channel) {
      continue;
    }
    // Серія швидких перемикань, яку Wokwi сам не моделює.
    const bool real_open = digitalRead(contact.pin) == HIGH;
    uint32_t accepted = 0;
    for (uint32_t i = 0; i < config::kSimBounceToggles; ++i) {
      const bool raw = (i % 2 == 0) ? !real_open : real_open;
      if (contact.filter.feed(raw, millis()) == DebounceResult::kChanged) {
        ++accepted;
      }
      delay(config::kSimBounceIntervalMs);
    }
    Serial.printf("[debounce] ch%u: %u toggles in %u ms, accepted changes %u\n",
                  channel, static_cast<unsigned>(config::kSimBounceToggles),
                  static_cast<unsigned>(config::kSimBounceToggles *
                                        config::kSimBounceIntervalMs),
                  static_cast<unsigned>(accepted));
    return true;
  }
  return false;
}

std::string NodeApp::inject_forged_command() {
  if (!commands_enabled_) {
    return "no command key: nothing to verify\n";
  }
  Command forged;
  forged.id = "forged-" + std::to_string(++forged_commands_);
  forged.type = "disarm";
  forged.payload = "{\"mode\":\"disarmed\"}";
  forged.nonce = last_nonce_ + 1;
  forged.issued_at = clock_.synced() ? clock_.now(millis()) : 0;
  forged.signature = std::string(kSha256DigestBytes * 2, 'f');
  const CommandVerifier verifier(command_key_, node_id_);
  const VerifyResult result = verifier.verify(
      forged, clock_.synced(), clock_.now(millis()), last_nonce_);
  // Підроблена команда не виконується й не підтверджується серверу.
  return "forged disarm: " + std::string(verify_result_name(result)) +
         ", mode stays " + mode_name(machine_.mode()) + "\n";
}
