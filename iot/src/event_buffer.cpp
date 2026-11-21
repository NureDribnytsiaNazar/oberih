#include "event_buffer.h"

#include <cstring>

namespace {

constexpr const char* kKeyEvents = "events";
constexpr const char* kKeySeq = "seq";
constexpr uint32_t kFormatMagic = 0x4F424531;  // "OBE1": версія формату

// Знімок буфера в NVS: події від найстарішої, без позиції голови.
struct Snapshot {
  uint32_t magic;
  uint32_t count;
  BufferedEvent items[EventBuffer::kCapacity];
};

}  // namespace

EventBuffer::EventBuffer(KeyValueStore& store) : store_(store) {}

void EventBuffer::load() {
  uint64_t seq = 0;
  if (store_.read_u64(kKeySeq, &seq)) {
    last_seq_ = seq;
  }
  static Snapshot snapshot;  // ~1,5 КБ: не на стеку
  if (!store_.read_blob(kKeyEvents, &snapshot, sizeof(snapshot)) ||
      snapshot.magic != kFormatMagic || snapshot.count > kCapacity) {
    head_ = 0;
    count_ = 0;
    return;
  }
  head_ = 0;
  count_ = snapshot.count;
  for (size_t i = 0; i < count_; ++i) {
    items_[i] = snapshot.items[i];
    // Відлік millis() попереднього запуску вже не співвідноситься з годинником.
    items_[i].flags &= static_cast<uint8_t>(~kFlagThisBoot);
  }
}

uint64_t EventBuffer::push(uint8_t channel, EventType type, bool is_alarm,
                           const NodeClock& clock, uint32_t now_ms) {
  if (count_ == kCapacity) {
    drop_for_new_event();
  }
  BufferedEvent event{};
  event.seq = ++last_seq_;
  event.epoch_s = clock.synced() ? clock.epoch_at(now_ms) : 0;
  event.uptime_ms = now_ms;
  event.channel = channel;
  event.type = type;
  event.flags = kFlagThisBoot;
  if (is_alarm) {
    event.flags |= kFlagAlarm;
  }
  items_[physical(count_)] = event;
  ++count_;
  save_seq();
  persist();
  return event.seq;
}

void EventBuffer::resolve_times(const NodeClock& clock) {
  if (!clock.synced()) {
    return;
  }
  bool changed = false;
  for (size_t i = 0; i < count_; ++i) {
    BufferedEvent& event = items_[physical(i)];
    if (event.epoch_s != 0) {
      continue;
    }
    if (event.flags & kFlagThisBoot) {
      event.epoch_s = clock.epoch_at(event.uptime_ms);
    } else {
      // Подія з попереднього запуску: точний час втрачено, беремо момент
      // синхронізації й позначаємо час як наближений.
      event.epoch_s = clock.synced_epoch();
      event.flags |= kFlagApproxTime;
    }
    changed = true;
  }
  if (changed) {
    persist();
  }
}

bool EventBuffer::adopt_server_seq(uint64_t server_last_seq) {
  if (server_last_seq <= last_seq_) {
    return false;
  }
  // Лічильник вузла позаду сервера (NVS очищено). Ненадіслані події ще не
  // бачив сервер, тож їм можна безпечно дати нові номери.
  uint64_t seq = server_last_seq;
  for (size_t i = 0; i < count_; ++i) {
    items_[physical(i)].seq = ++seq;
  }
  last_seq_ = seq;
  save_seq();
  persist();
  return true;
}

size_t EventBuffer::peek(BufferedEvent* out, size_t max_count) const {
  size_t copied = 0;
  while (copied < count_ && copied < max_count) {
    const BufferedEvent& event = items_[physical(copied)];
    if (event.epoch_s == 0) {
      break;  // без часу подію не надсилаємо; порядок зберігається
    }
    out[copied] = event;
    ++copied;
  }
  return copied;
}

void EventBuffer::pop(size_t count) {
  if (count > count_) {
    count = count_;
  }
  head_ = physical(count);
  count_ -= count;
  persist();
}

const BufferedEvent& EventBuffer::at(size_t index) const {
  return items_[physical(index)];
}

void EventBuffer::drop_for_new_event() {
  for (size_t i = 0; i < count_; ++i) {
    if ((items_[physical(i)].flags & kFlagAlarm) == 0) {
      remove_at(i);
      ++dropped_;
      return;
    }
  }
  // Усі події тривожні — відкидаємо найстарішу.
  remove_at(0);
  ++dropped_;
}

void EventBuffer::remove_at(size_t index) {
  for (size_t i = index; i + 1 < count_; ++i) {
    items_[physical(i)] = items_[physical(i + 1)];
  }
  --count_;
}

void EventBuffer::persist() {
  static Snapshot snapshot;
  std::memset(&snapshot, 0, sizeof(snapshot));
  snapshot.magic = kFormatMagic;
  snapshot.count = static_cast<uint32_t>(count_);
  for (size_t i = 0; i < count_; ++i) {
    snapshot.items[i] = items_[physical(i)];
  }
  if (!store_.write_blob(kKeyEvents, &snapshot, sizeof(snapshot))) {
    ++storage_errors_;
  }
}

void EventBuffer::save_seq() {
  if (!store_.write_u64(kKeySeq, last_seq_)) {
    ++storage_errors_;
  }
}
