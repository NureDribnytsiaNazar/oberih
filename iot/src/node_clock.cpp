#include "node_clock.h"

namespace {
constexpr int64_t kMsPerSecond = 1000;
}

void NodeClock::sync(int64_t server_epoch_s, uint32_t now_ms) {
  sync_epoch_s_ = server_epoch_s;
  sync_uptime_ms_ = now_ms;
  synced_ = true;
}

int64_t NodeClock::epoch_at(uint32_t uptime_ms) const {
  // Знакова різниця: момент може бути як до, так і після синхронізації.
  const int64_t delta_ms =
      static_cast<int32_t>(uptime_ms - sync_uptime_ms_);
  return sync_epoch_s_ + delta_ms / kMsPerSecond;
}
