#include "mode_machine.h"

namespace {

constexpr uint32_t kMsPerSecond = 1000;

bool is_armed(Mode mode) {
  return mode == Mode::kArmedAway || mode == Mode::kArmedHome;
}

bool is_disarmable(Mode mode) { return mode != Mode::kDisarmed; }

// Таблиця переходів без урахування нульових затримок.
bool raw_target(Mode current, Trigger trigger, Mode* out) {
  switch (trigger) {
    case Trigger::kInstantAlarm:
      *out = Mode::kAlarm;
      return true;
    case Trigger::kDisarm:
      *out = Mode::kDisarmed;
      return is_disarmable(current);
    case Trigger::kArmAway:
      *out = Mode::kExitDelay;
      return current == Mode::kDisarmed;
    case Trigger::kArmHome:
      *out = Mode::kArmedHome;
      return current == Mode::kDisarmed;
    case Trigger::kExitDelayExpired:
      *out = Mode::kArmedAway;
      return current == Mode::kExitDelay;
    case Trigger::kIntrusion:
      *out = Mode::kEntryDelay;
      return is_armed(current);
    case Trigger::kEntryDelayExpired:
      *out = Mode::kAlarm;
      return current == Mode::kEntryDelay;
  }
  return false;
}

// Чи обробляється спрацювання датчика в режимі (як is_monitored на сервері).
bool is_monitored(Mode mode, SensorKind sensor, ZoneKind zone) {
  if (!is_armed(mode)) {
    return false;
  }
  if (mode == Mode::kArmedHome) {
    // «Вдома»: внутрішні зони й датчики руху виключено.
    return zone != ZoneKind::kInterior && sensor != SensorKind::kPir;
  }
  return true;
}

}  // namespace

bool next_mode(Mode current, Trigger trigger, uint32_t delay_s, Mode* out) {
  Mode target = current;
  if (!raw_target(current, trigger, &target)) {
    return false;
  }
  if (delay_s == 0 && target == Mode::kExitDelay) {
    target = Mode::kArmedAway;
  } else if (delay_s == 0 && target == Mode::kEntryDelay) {
    target = Mode::kAlarm;
  }
  *out = target;
  return true;
}

bool ModeMachine::apply(Trigger trigger, const Delays& delays, uint32_t now_ms) {
  uint32_t delay_s = 0;
  if (trigger == Trigger::kArmAway) {
    delay_s = delays.exit_delay_s;
  } else if (trigger == Trigger::kIntrusion) {
    delay_s = delays.entry_delay_s;
  }
  Mode target = mode_;
  if (!next_mode(mode_, trigger, delay_s, &target)) {
    return false;
  }
  if (target != mode_) {
    mode_ = target;
    changed_at_ms_ = now_ms;
  }
  return true;
}

bool ModeMachine::tick(const Delays& delays, uint32_t now_ms) {
  const uint32_t elapsed_ms = now_ms - changed_at_ms_;
  if (mode_ == Mode::kExitDelay &&
      elapsed_ms >= delays.exit_delay_s * kMsPerSecond) {
    return apply(Trigger::kExitDelayExpired, delays, now_ms);
  }
  if (mode_ == Mode::kEntryDelay &&
      elapsed_ms >= delays.entry_delay_s * kMsPerSecond) {
    return apply(Trigger::kEntryDelayExpired, delays, now_ms);
  }
  return false;
}

bool ModeMachine::on_sensor_trigger(SensorKind sensor, ZoneKind zone,
                                    const Delays& delays, uint32_t now_ms) {
  const Mode before = mode_;
  if (sensor == SensorKind::kTamper || zone == ZoneKind::kAlwaysOn) {
    apply(Trigger::kInstantAlarm, delays, now_ms);
  } else if (is_monitored(mode_, sensor, zone)) {
    apply(Trigger::kIntrusion, delays, now_ms);
  }
  return mode_ != before;
}

void ModeMachine::force(Mode mode, uint32_t now_ms) {
  if (mode != mode_) {
    mode_ = mode;
    changed_at_ms_ = now_ms;
  }
}
