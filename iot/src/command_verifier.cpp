#include "command_verifier.h"

#include <cstring>

#include "sha256.h"

const char* verify_result_name(VerifyResult result) {
  switch (result) {
    case VerifyResult::kAccepted:
      return "accepted";
    case VerifyResult::kBadSignature:
      return "bad_signature";
    case VerifyResult::kClockNotSynced:
      return "clock_not_synced";
    case VerifyResult::kExpired:
      return "expired";
    case VerifyResult::kReplay:
      return "replay";
  }
  return "unknown";
}

std::string command_signing_string(const std::string& node_id,
                                   const Command& command) {
  return node_id + "|" + std::to_string(command.nonce) + "|" + command.type +
         "|" + command.payload + "|" + std::to_string(command.issued_at);
}

CommandVerifier::CommandVerifier(const uint8_t* key, const std::string& node_id)
    : node_id_(node_id) {
  std::memcpy(key_, key, sizeof(key_));
}

std::string CommandVerifier::sign(const Command& command) const {
  const std::string message = command_signing_string(node_id_, command);
  uint8_t digest[kSha256DigestBytes];
  hmac_sha256(key_, sizeof(key_),
              reinterpret_cast<const uint8_t*>(message.data()), message.size(),
              digest);
  return to_hex(digest, sizeof(digest));
}

VerifyResult CommandVerifier::verify(const Command& command, bool clock_synced,
                                     int64_t now_epoch_s,
                                     uint64_t last_nonce) const {
  // Спершу підпис: підроблена команда не повинна впливати ні на що інше.
  if (!constant_time_equal(sign(command), command.signature)) {
    return VerifyResult::kBadSignature;
  }
  if (!clock_synced) {
    return VerifyResult::kClockNotSynced;
  }
  const int64_t skew = now_epoch_s - command.issued_at;
  if (skew > config::kCommandMaxSkewS || -skew > config::kCommandMaxSkewS) {
    return VerifyResult::kExpired;
  }
  if (command.nonce <= last_nonce) {
    return VerifyResult::kReplay;
  }
  return VerifyResult::kAccepted;
}

bool command_target_mode(const std::string& type, const std::string& mode_name,
                         Mode* out) {
  Mode mode = Mode::kDisarmed;
  if (!parse_mode(mode_name.c_str(), &mode)) {
    return false;
  }
  const bool matches =
      (type == "disarm" && mode == Mode::kDisarmed) ||
      (type == "arm_home" && mode == Mode::kArmedHome) ||
      (type == "arm_away" &&
       (mode == Mode::kExitDelay || mode == Mode::kArmedAway));
  if (matches) {
    *out = mode;
  }
  return matches;
}
