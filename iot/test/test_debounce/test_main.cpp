// ІК-2: фільтр брязкоту геркона.
#include <unity.h>

#include "debounce.h"

namespace {
constexpr uint32_t kDebounceMs = 50;
}

void setUp() {}
void tearDown() {}

void test_bounce_is_rejected() {
  Debouncer filter(false, kDebounceMs);
  // Швидкі перемикання кожні 5 мс не дають стабільного значення.
  for (uint32_t t = 0; t < 40; t += 5) {
    const bool raw = (t / 5) % 2 == 0;
    TEST_ASSERT_EQUAL(DebounceResult::kNoChange, filter.feed(raw, t));
  }
  TEST_ASSERT_FALSE(filter.stable());
}

void test_stable_change_is_accepted() {
  Debouncer filter(false, kDebounceMs);
  TEST_ASSERT_EQUAL(DebounceResult::kNoChange, filter.feed(true, 100));
  TEST_ASSERT_EQUAL(DebounceResult::kNoChange, filter.feed(true, 120));
  TEST_ASSERT_EQUAL(DebounceResult::kChanged, filter.feed(true, 160));
  TEST_ASSERT_TRUE(filter.stable());
  // Подальші однакові відліки зміни не дають.
  TEST_ASSERT_EQUAL(DebounceResult::kNoChange, filter.feed(true, 300));
}

void test_boundary_exactly_debounce_ms() {
  Debouncer filter(false, kDebounceMs);
  filter.feed(true, 1000);
  TEST_ASSERT_EQUAL(DebounceResult::kNoChange, filter.feed(true, 1049));
  TEST_ASSERT_EQUAL(DebounceResult::kChanged, filter.feed(true, 1050));
}

void test_bounce_restarts_stability_window() {
  Debouncer filter(false, kDebounceMs);
  filter.feed(true, 0);
  filter.feed(false, 30);  // повернення у стабільний стан скидає кандидата
  TEST_ASSERT_EQUAL(DebounceResult::kNoChange, filter.feed(true, 40));
  TEST_ASSERT_EQUAL(DebounceResult::kNoChange, filter.feed(true, 60));
  TEST_ASSERT_EQUAL(DebounceResult::kChanged, filter.feed(true, 90));
}

void test_works_across_millis_overflow() {
  Debouncer filter(false, kDebounceMs);
  const uint32_t near_max = 0xFFFFFFF0;
  filter.feed(true, near_max);
  TEST_ASSERT_EQUAL(DebounceResult::kChanged, filter.feed(true, 40));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_bounce_is_rejected);
  RUN_TEST(test_stable_change_is_accepted);
  RUN_TEST(test_boundary_exactly_debounce_ms);
  RUN_TEST(test_bounce_restarts_stability_window);
  RUN_TEST(test_works_across_millis_overflow);
  return UNITY_END();
}
