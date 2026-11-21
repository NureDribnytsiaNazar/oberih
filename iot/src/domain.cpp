#include "domain.h"

#include <cstring>

namespace {

struct ModeName {
  Mode mode;
  const char* name;
};

constexpr ModeName kModeNames[] = {
    {Mode::kDisarmed, "disarmed"},     {Mode::kExitDelay, "exit_delay"},
    {Mode::kArmedAway, "armed_away"},  {Mode::kArmedHome, "armed_home"},
    {Mode::kEntryDelay, "entry_delay"}, {Mode::kAlarm, "alarm"},
};

}  // namespace

const char* mode_name(Mode mode) {
  for (const ModeName& item : kModeNames) {
    if (item.mode == mode) {
      return item.name;
    }
  }
  return "unknown";
}

bool parse_mode(const char* name, Mode* out) {
  if (name == nullptr) {
    return false;
  }
  for (const ModeName& item : kModeNames) {
    if (std::strcmp(item.name, name) == 0) {
      *out = item.mode;
      return true;
    }
  }
  return false;
}

const char* event_type_name(EventType type) {
  switch (type) {
    case EventType::kOpened:
      return "opened";
    case EventType::kClosed:
      return "closed";
    case EventType::kMotion:
      return "motion";
    case EventType::kTamper:
      return "tamper";
    case EventType::kTamperRestored:
      return "tamper_restored";
  }
  return "unknown";
}

bool is_trigger_event(EventType type) {
  return type == EventType::kOpened || type == EventType::kMotion ||
         type == EventType::kTamper;
}
