#include "backoff.h"

namespace {

constexpr uint32_t kMaxShift = 31;
constexpr uint32_t kDefaultSeed = 0x9E3779B9;  // нульовий стан xorshift незмінний
constexpr int kHttpOkFirst = 200;
constexpr int kHttpOkLast = 299;
constexpr int kHttpUnauthorized = 401;
constexpr int kHttpForbidden = 403;
constexpr int kHttpRequestTimeout = 408;
constexpr int kHttpTooManyRequests = 429;  // обмеження частоти в Nginx (ЛБ5)
constexpr int kHttpClientErrorFirst = 400;
constexpr int kHttpClientErrorLast = 499;

}  // namespace

Backoff::Backoff(uint32_t base_ms, uint32_t max_ms, uint32_t jitter_max_ms,
                 uint32_t seed)
    : base_ms_(base_ms),
      max_ms_(max_ms),
      jitter_max_ms_(jitter_max_ms),
      rng_state_(seed != 0 ? seed : kDefaultSeed) {}

uint32_t Backoff::next_delay_ms() {
  const uint32_t shift = attempts_ < kMaxShift ? attempts_ : kMaxShift;
  // Множення в 64 бітах, щоб base · 2^n не переповнилося.
  const uint64_t exponential = static_cast<uint64_t>(base_ms_) << shift;
  const uint32_t capped =
      exponential < max_ms_ ? static_cast<uint32_t>(exponential) : max_ms_;
  ++attempts_;
  return capped + next_jitter();
}

uint32_t Backoff::next_jitter() {
  if (jitter_max_ms_ == 0) {
    return 0;
  }
  rng_state_ ^= rng_state_ << 13;
  rng_state_ ^= rng_state_ >> 17;
  rng_state_ ^= rng_state_ << 5;
  return rng_state_ % (jitter_max_ms_ + 1);
}

SendOutcome classify_response(int status) {
  if (status >= kHttpOkFirst && status <= kHttpOkLast) {
    return SendOutcome::kDelivered;
  }
  if (status == kHttpRequestTimeout || status == kHttpTooManyRequests) {
    return SendOutcome::kRetry;
  }
  if (status == kHttpUnauthorized || status == kHttpForbidden) {
    return SendOutcome::kAuthFailed;
  }
  if (status >= kHttpClientErrorFirst && status <= kHttpClientErrorLast) {
    return SendOutcome::kRejected;
  }
  return SendOutcome::kRetry;
}
