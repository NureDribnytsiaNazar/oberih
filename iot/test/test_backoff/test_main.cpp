// ІК-5: затримки повторів і класифікація відповідей сервера.
#include <unity.h>

#include "backoff.h"
#include "config.h"

void setUp() {}
void tearDown() {}

void test_sequence_doubles_up_to_max() {
  Backoff backoff(config::kBackoffBaseMs, config::kBackoffMaxMs, 0, 1);
  const uint32_t expected[] = {1000,  2000,  4000,  8000,  16000,
                               32000, 60000, 60000, 60000};
  for (uint32_t delay : expected) {
    TEST_ASSERT_EQUAL_UINT32(delay, backoff.next_delay_ms());
  }
}

void test_reset_starts_from_base() {
  Backoff backoff(1000, 60000, 0, 1);
  backoff.next_delay_ms();
  backoff.next_delay_ms();
  backoff.reset();
  TEST_ASSERT_EQUAL_UINT32(1000, backoff.next_delay_ms());
}

void test_jitter_is_bounded_and_deterministic() {
  Backoff first(1000, 60000, 250, 42);
  Backoff second(1000, 60000, 250, 42);
  for (uint32_t attempt = 0; attempt < 20; ++attempt) {
    const uint32_t delay = first.next_delay_ms();
    TEST_ASSERT_EQUAL_UINT32(delay, second.next_delay_ms());
    const uint32_t base = attempt < 6 ? (1000U << attempt) : 60000U;
    TEST_ASSERT_TRUE(delay >= base && delay <= base + 250);
  }
}

void test_no_overflow_after_many_attempts() {
  Backoff backoff(1000, 60000, 0, 1);
  for (int i = 0; i < 100; ++i) {
    backoff.next_delay_ms();
  }
  TEST_ASSERT_EQUAL_UINT32(60000, backoff.next_delay_ms());
}

void test_classify_response() {
  TEST_ASSERT_EQUAL(SendOutcome::kDelivered, classify_response(200));
  TEST_ASSERT_EQUAL(SendOutcome::kRetry, classify_response(500));
  TEST_ASSERT_EQUAL(SendOutcome::kRetry, classify_response(503));
  TEST_ASSERT_EQUAL(SendOutcome::kRetry, classify_response(-1));  // таймаут
  TEST_ASSERT_EQUAL(SendOutcome::kRetry, classify_response(429));
  TEST_ASSERT_EQUAL(SendOutcome::kAuthFailed, classify_response(401));
  TEST_ASSERT_EQUAL(SendOutcome::kAuthFailed, classify_response(403));
  TEST_ASSERT_EQUAL(SendOutcome::kRejected, classify_response(400));
  TEST_ASSERT_EQUAL(SendOutcome::kRejected, classify_response(422));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_sequence_doubles_up_to_max);
  RUN_TEST(test_reset_starts_from_base);
  RUN_TEST(test_jitter_is_bounded_and_deterministic);
  RUN_TEST(test_no_overflow_after_many_attempts);
  RUN_TEST(test_classify_response);
  return UNITY_END();
}
