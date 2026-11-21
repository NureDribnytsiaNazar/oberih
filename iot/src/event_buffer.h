// ІК-4: кільцевий буфер подій у NVS.
// Порядковий номер (seq) наскрізний і переживає перезавантаження. При
// переповненні відкидається найстаріша не тривожна подія; тривожні мають
// пріоритет. Після відновлення зв'язку події надсилаються пакетом зі
// своїми початковими мітками часу.
#pragma once

#include <cstddef>
#include <cstdint>

#include "config.h"
#include "domain.h"
#include "node_clock.h"
#include "storage.h"

struct BufferedEvent {
  uint64_t seq;
  int64_t epoch_s;     // 0 — час ще невідомий (до синхронізації годинника)
  uint32_t uptime_ms;  // момент події за millis() запуску, у якому вона сталася
  uint8_t channel;
  EventType type;
  uint8_t flags;  // див. kFlag*
};

class EventBuffer {
 public:
  static constexpr uint8_t kFlagAlarm = 1;        // тривожна подія
  static constexpr uint8_t kFlagThisBoot = 2;     // uptime_ms цього запуску
  static constexpr uint8_t kFlagApproxTime = 4;   // час відновлено наближено
  static constexpr size_t kCapacity = config::kEventBufferCapacity;

  explicit EventBuffer(KeyValueStore& store);

  // Відновлює буфер і лічильник seq зі сховища (після перезавантаження).
  void load();

  // Додає подію й повертає її seq. Час — з годинника, якщо він синхронізований.
  uint64_t push(uint8_t channel, EventType type, bool is_alarm,
                const NodeClock& clock, uint32_t now_ms);

  // Проставляє час подіям, що сталися до синхронізації годинника.
  void resolve_times(const NodeClock& clock);

  // Лічильник сервера більший за локальний (NVS очищено, наприклад новий
  // запуск симуляції): ненадіслані події отримують номери після нього.
  // true — номери змінено.
  bool adopt_server_seq(uint64_t server_last_seq);

  // Копіює до max_count найстаріших подій із відомим часом; повертає кількість.
  size_t peek(BufferedEvent* out, size_t max_count) const;

  // Видаляє count найстаріших подій (сервер їх прийняв).
  void pop(size_t count);

  size_t size() const { return count_; }
  uint64_t last_seq() const { return last_seq_; }
  uint32_t dropped() const { return dropped_; }
  uint32_t storage_errors() const { return storage_errors_; }
  const BufferedEvent& at(size_t index) const;

 private:
  size_t physical(size_t index) const { return (head_ + index) % kCapacity; }
  void drop_for_new_event();
  void remove_at(size_t index);
  void persist();
  void save_seq();

  KeyValueStore& store_;
  BufferedEvent items_[kCapacity] = {};
  size_t head_ = 0;
  size_t count_ = 0;
  uint64_t last_seq_ = 0;
  uint32_t dropped_ = 0;
  uint32_t storage_errors_ = 0;
};
