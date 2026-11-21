#include "debounce.h"

Debouncer::Debouncer(bool initial_state, uint32_t debounce_ms)
    : stable_(initial_state), debounce_ms_(debounce_ms) {}

DebounceResult Debouncer::feed(bool raw, uint32_t now_ms) {
  if (raw == stable_) {
    // Брязкіт повернув контакт у стабільний стан — кандидата відкидаємо.
    has_candidate_ = false;
    return DebounceResult::kNoChange;
  }
  if (!has_candidate_ || candidate_ != raw) {
    candidate_ = raw;
    candidate_since_ms_ = now_ms;
    has_candidate_ = true;
  }
  // Різниця беззнакових чисел коректна й після переповнення millis().
  if (now_ms - candidate_since_ms_ < debounce_ms_) {
    return DebounceResult::kNoChange;
  }
  stable_ = raw;
  has_candidate_ = false;
  return DebounceResult::kChanged;
}
