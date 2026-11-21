// Програма вузла: склеює модулі в цикл
// датчики -> фільтри -> автомат -> буфер -> передавання з повторами ->
// heartbeat -> команди -> індикація (рисунок docs/diagrams/iot-activity).
#pragma once

#include <cstdint>
#include <string>
#include <vector>

#include "backoff.h"
#include "command_verifier.h"
#include "console.h"
#include "debounce.h"
#include "domain.h"
#include "event_buffer.h"
#include "indicators.h"
#include "mode_machine.h"
#include "motion_lockout.h"
#include "net_client.h"
#include "node_clock.h"
#include "nvs_storage.h"
#include "protocol.h"
#include "settings.h"

class NodeApp : public ConsoleActions {
 public:
  NodeApp();

  void begin();
  void loop();

  // ConsoleActions
  bool save_settings(const NodeSettings& settings) override;
  void settings_changed() override;
  std::string status() override;
  std::string buffer_dump() override;
  void set_network_enabled(bool enabled) override;
  bool simulate_bounce(uint8_t channel) override;
  std::string inject_forged_command() override;

 private:
  // Геркон або тампер: цифровий вхід із фільтром брязкоту.
  struct ContactInput {
    ChannelInfo info;
    uint8_t pin;
    EventType active_event;    // подія, коли контакт розімкнено
    EventType inactive_event;  // подія, коли контакт знову замкнено
    Debouncer filter;
  };

  void load_state();
  void load_command_key();
  Delays delays() const;

  void poll_console();
  void poll_contacts(uint32_t now_ms);
  void poll_pir(uint32_t now_ms);
  void record_event(const ChannelInfo& info, EventType type, uint32_t now_ms);

  void service_wifi(uint32_t now_ms);
  void service_heartbeat(uint32_t now_ms);
  void service_events(uint32_t now_ms);
  void heartbeat_succeeded(const HeartbeatReply& reply, uint32_t now_ms);
  void heartbeat_failed(int status, uint32_t now_ms);
  void apply_server_settings(const NodeSettings& incoming, const char* source);
  void process_command(const Command& command, uint32_t now_ms);
  void execute_command(const Command& command, uint32_t now_ms);

  void update_indicators(uint32_t now_ms);
  bool online() const { return missed_polls_ < config::kMissedPollsLimit; }

  NvsStore store_;
  NodeSettings settings_;
  ModeMachine machine_;
  EventBuffer buffer_;
  NodeClock clock_;
  NetClient net_;
  Console console_;
  Backoff heartbeat_backoff_;
  Backoff events_backoff_;
  ContactInput contacts_[3];
  ChannelInfo pir_info_;
  MotionLockout pir_lockout_;
  bool pir_level_ = false;

  std::string node_id_;
  uint8_t command_key_[config::kCommandKeyBytes] = {};
  bool commands_enabled_ = false;
  uint64_t last_nonce_ = 0;
  std::vector<std::string> pending_acks_;
  uint32_t forged_commands_ = 0;

  bool network_enabled_ = true;
  bool wifi_was_connected_ = false;
  uint32_t next_wifi_attempt_ms_ = 0;
  uint32_t next_heartbeat_ms_ = 0;
  uint32_t next_events_ms_ = 0;
  uint32_t missed_polls_ = 0;
  uint32_t rejected_attempts_ = 0;
  bool restored_ = false;
  uint32_t restored_at_ms_ = 0;
  Mode reported_mode_ = Mode::kDisarmed;
  uint16_t current_tone_hz_ = 0;
  std::string console_line_;
};
