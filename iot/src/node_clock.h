// Час вузла в секундах Unix (UTC).
// Годиннику ESP32 не довіряємо: час береться з server_epoch відповіді
// heartbeat і далі відлічується від millis().
#pragma once

#include <cstdint>

class NodeClock {
 public:
  void sync(int64_t server_epoch_s, uint32_t now_ms);

  bool synced() const { return synced_; }
  // Час Unix для моменту uptime_ms (millis() поточного запуску).
  int64_t epoch_at(uint32_t uptime_ms) const;
  int64_t now(uint32_t now_ms) const { return epoch_at(now_ms); }
  // Час Unix у момент останньої синхронізації.
  int64_t synced_epoch() const { return sync_epoch_s_; }

 private:
  bool synced_ = false;
  int64_t sync_epoch_s_ = 0;
  uint32_t sync_uptime_ms_ = 0;
};
