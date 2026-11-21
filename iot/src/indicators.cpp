#include "indicators.h"

#include "config.h"

namespace {

// Перша половина періоду — увімкнено.
bool blink_on(uint32_t now_ms, uint32_t period_ms) {
  return now_ms % period_ms < period_ms / 2;
}

IndicatorOutput mode_pattern(Mode mode, uint32_t now_ms) {
  IndicatorOutput out{false, false, false, 0};
  switch (mode) {
    case Mode::kDisarmed:
      out.green = true;
      break;
    case Mode::kArmedHome:
      out.red = true;
      out.green = true;
      break;
    case Mode::kArmedAway:
      out.red = true;
      break;
    case Mode::kExitDelay:
    case Mode::kEntryDelay:
      out.red = blink_on(now_ms, config::kDelayBlinkPeriodMs);
      break;
    case Mode::kAlarm:
      out.red = blink_on(now_ms, config::kAlarmBlinkPeriodMs);
      out.tone_hz = config::kAlarmToneHz;
      break;
  }
  return out;
}

}  // namespace

IndicatorOutput indicator_state(const IndicatorInput& input) {
  IndicatorOutput out = mode_pattern(input.mode, input.now_ms);
  const bool alarm = input.mode == Mode::kAlarm;
  if (input.offline) {
    // Синій спалах перекриває колір режиму в першій половині секунди.
    if (blink_on(input.now_ms, config::kOfflineBlinkPeriodMs)) {
      out = {false, false, true, out.tone_hz};
    }
    if (!alarm &&
        input.now_ms % config::kOfflineBeepPeriodMs < config::kOfflineBeepMs) {
      out.tone_hz = config::kNoticeToneHz;
    }
    return out;
  }
  const uint32_t since_restore = input.now_ms - input.restored_at_ms;
  if (input.restored && since_restore < config::kRestoredIndicationMs) {
    out.blue = true;
    if (!alarm && since_restore < config::kOfflineBeepMs) {
      out.tone_hz = config::kNoticeToneHz;
    }
  }
  return out;
}
