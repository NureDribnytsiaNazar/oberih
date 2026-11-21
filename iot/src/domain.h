// Типи предметної області вузла та їхні назви в API сервера.
#pragma once

#include <cstdint>

// Режими охорони (рисунок 2 Vision & Scope, FacilityMode на сервері).
enum class Mode : uint8_t {
  kDisarmed,
  kExitDelay,
  kArmedAway,
  kArmedHome,
  kEntryDelay,
  kAlarm,
};

// Типи подій, які формує вузол (DEVICE_EVENT_TYPES на сервері).
enum class EventType : uint8_t {
  kOpened,
  kClosed,
  kMotion,
  kTamper,
  kTamperRestored,
};

enum class SensorKind : uint8_t { kReed, kPir, kTamper };

enum class ZoneKind : uint8_t { kPerimeter, kInterior, kAlwaysOn };

// Опис каналу вузла: який датчик і в якій зоні.
struct ChannelInfo {
  uint8_t channel;
  SensorKind sensor;
  ZoneKind zone;
};

const char* mode_name(Mode mode);
bool parse_mode(const char* name, Mode* out);
const char* event_type_name(EventType type);
// Подія означає спрацювання датчика (відкриття, рух, тампер).
bool is_trigger_event(EventType type);
