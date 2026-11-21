// ІК-3: блокування повторних спрацювань датчика руху.
// Після прийнятого спрацювання наступні ігноруються протягом lockout.
#pragma once

#include <cstdint>

class MotionLockout {
 public:
  explicit MotionLockout(uint32_t lockout_s);

  // true — спрацювання прийнято (і починається новий інтервал блокування),
  // false — воно потрапило в інтервал блокування й відкидається.
  bool accept(uint32_t now_ms);

  void set_lockout_s(uint32_t lockout_s) { lockout_ms_ = lockout_s * 1000U; }

 private:
  uint32_t lockout_ms_;
  uint32_t last_accepted_ms_ = 0;
  bool has_last_ = false;
};
