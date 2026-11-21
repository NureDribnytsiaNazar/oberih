// ІК-5: повтори зі зростаючою затримкою.
// delay(n) = min(base · 2^n, max) + jitter, де jitter — детерміноване ціле
// з [0, jitter_max] (генератор xorshift32 із заданим зерном).
#pragma once

#include <cstdint>

class Backoff {
 public:
  Backoff(uint32_t base_ms, uint32_t max_ms, uint32_t jitter_max_ms,
          uint32_t seed);

  // Затримка перед наступною спробою після чергової невдачі.
  uint32_t next_delay_ms();
  // Успішна спроба: наступна невдача знову почнеться з base.
  void reset() { attempts_ = 0; }
  uint32_t attempts() const { return attempts_; }

 private:
  uint32_t next_jitter();

  uint32_t base_ms_;
  uint32_t max_ms_;
  uint32_t jitter_max_ms_;
  uint32_t rng_state_;
  uint32_t attempts_ = 0;
};

// Що робити з пакетом після відповіді сервера.
enum class SendOutcome : uint8_t {
  kDelivered,   // 2xx — пакет прийнято
  kRetry,       // 5xx, 408, 429, немає зв'язку — повторити, подій не втрачати
  kAuthFailed,  // 401/403 — повторювати з максимальною затримкою
  kRejected,    // інші 4xx — пакет некоректний, не повторювати вічно
};

// status — HTTP-код або від'ємний код помилки з'єднання.
SendOutcome classify_response(int status);
