// ІК-7: перевірка команд сервера перед виконанням.
// Команда виконується, лише якщо: підпис HMAC-SHA256 збігається
// (порівняння сталого часу), |now − issued_at| ≤ 60 с за годинником,
// синхронізованим із сервером, і nonce строго більший за останній прийнятий.
#pragma once

#include <cstdint>
#include <string>

#include "config.h"
#include "domain.h"

// Команда з відповіді heartbeat (поля NodeCommandOut на сервері).
struct Command {
  std::string id;
  std::string type;     // arm_away | arm_home | disarm | set_config
  std::string payload;  // канонічний JSON, над яким обчислено підпис
  uint64_t nonce = 0;
  int64_t issued_at = 0;  // секунди Unix
  std::string signature;  // hex
};

enum class VerifyResult : uint8_t {
  kAccepted,
  kBadSignature,
  kClockNotSynced,
  kExpired,
  kReplay,
};

const char* verify_result_name(VerifyResult result);

// Рядок підпису: "<node_id>|<nonce>|<type>|<payload>|<issued_at>".
std::string command_signing_string(const std::string& node_id,
                                   const Command& command);

class CommandVerifier {
 public:
  // key — 32 байти ключа підпису з введення вузла в експлуатацію.
  CommandVerifier(const uint8_t* key, const std::string& node_id);

  std::string sign(const Command& command) const;

  VerifyResult verify(const Command& command, bool clock_synced,
                      int64_t now_epoch_s, uint64_t last_nonce) const;

 private:
  uint8_t key_[config::kCommandKeyBytes];
  std::string node_id_;
};

// Режим, якого вимагає команда керування охороною. false — тип команди не
// змінює режим або режим у payload не відповідає типу.
bool command_target_mode(const std::string& type, const std::string& mode_name,
                         Mode* out);
