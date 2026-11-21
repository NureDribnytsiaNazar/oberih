// ІК-2: фільтр брязкоту контактів геркона.
// Зміна стану приймається, якщо нове значення стабільне не менше debounce_ms.
#pragma once

#include <cstdint>

enum class DebounceResult : uint8_t { kNoChange, kChanged };

class Debouncer {
 public:
  Debouncer(bool initial_state, uint32_t debounce_ms);

  // Подає сирий відлік у момент now_ms. Повертає kChanged, коли нове
  // значення протрималося debounce_ms; тоді stable() вже містить його.
  DebounceResult feed(bool raw, uint32_t now_ms);

  bool stable() const { return stable_; }
  void set_debounce_ms(uint32_t debounce_ms) { debounce_ms_ = debounce_ms; }

 private:
  bool stable_;
  bool candidate_ = false;
  bool has_candidate_ = false;
  uint32_t candidate_since_ms_ = 0;
  uint32_t debounce_ms_;
};
