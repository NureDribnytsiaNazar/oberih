// ІК-1: локальний автомат режимів охорони.
// Переходи ті самі, що в server/app/services/state_machine.py; автомат
// працює без зв'язку із сервером. Тампер і цілодобова зона дають тривогу
// в будь-якому режимі.
#pragma once

#include <cstdint>

#include "domain.h"

enum class Trigger : uint8_t {
  kArmAway,
  kArmHome,
  kExitDelayExpired,
  kIntrusion,
  kInstantAlarm,
  kEntryDelayExpired,
  kDisarm,
};

// Тривалості затримок виходу й входу (з налаштувань вузла).
struct Delays {
  uint32_t exit_delay_s;
  uint32_t entry_delay_s;
};

// Чистий перехід: false, якщо пара (режим, тригер) недопустима.
// delay_s — тривалість затримки, у яку веде перехід; нульова пропускає її.
bool next_mode(Mode current, Trigger trigger, uint32_t delay_s, Mode* out);

class ModeMachine {
 public:
  explicit ModeMachine(Mode initial = Mode::kDisarmed) : mode_(initial) {}

  // Застосовує тригер. Повертає false для недопустимого переходу.
  bool apply(Trigger trigger, const Delays& delays, uint32_t now_ms);

  // Завершує затримку, якщо її час минув. true — режим змінився.
  bool tick(const Delays& delays, uint32_t now_ms);

  // Спрацювання датчика. true — режим змінився (подія тривожна).
  bool on_sensor_trigger(SensorKind sensor, ZoneKind zone, const Delays& delays,
                         uint32_t now_ms);

  // Встановлює режим за перевіреною командою сервера (джерело істини).
  void force(Mode mode, uint32_t now_ms);

  Mode mode() const { return mode_; }
  uint32_t changed_at_ms() const { return changed_at_ms_; }

 private:
  Mode mode_;
  uint32_t changed_at_ms_ = 0;
};
