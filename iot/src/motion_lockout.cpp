#include "motion_lockout.h"

MotionLockout::MotionLockout(uint32_t lockout_s) : lockout_ms_(lockout_s * 1000U) {}

bool MotionLockout::accept(uint32_t now_ms) {
  if (has_last_ && now_ms - last_accepted_ms_ < lockout_ms_) {
    return false;
  }
  last_accepted_ms_ = now_ms;
  has_last_ = true;
  return true;
}
