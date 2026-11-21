// ІК-3: блокування повторних спрацювань PIR.
#include <unity.h>

#include "motion_lockout.h"

void setUp() {}
void tearDown() {}

void test_first_trigger_is_accepted() {
  MotionLockout lockout(10);
  TEST_ASSERT_TRUE(lockout.accept(5000));
}

void test_repeats_inside_lockout_are_ignored() {
  MotionLockout lockout(10);
  lockout.accept(0);
  TEST_ASSERT_FALSE(lockout.accept(1000));
  TEST_ASSERT_FALSE(lockout.accept(9999));
}

void test_boundary_exactly_lockout() {
  MotionLockout lockout(10);
  lockout.accept(0);
  TEST_ASSERT_TRUE(lockout.accept(10000));
  // Новий інтервал рахується від останнього прийнятого спрацювання.
  TEST_ASSERT_FALSE(lockout.accept(19999));
  TEST_ASSERT_TRUE(lockout.accept(20000));
}

void test_zero_lockout_accepts_everything() {
  MotionLockout lockout(0);
  TEST_ASSERT_TRUE(lockout.accept(0));
  TEST_ASSERT_TRUE(lockout.accept(0));
}

void test_lockout_can_be_changed() {
  MotionLockout lockout(10);
  lockout.accept(0);
  lockout.set_lockout_s(2);
  TEST_ASSERT_TRUE(lockout.accept(2000));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_first_trigger_is_accepted);
  RUN_TEST(test_repeats_inside_lockout_are_ignored);
  RUN_TEST(test_boundary_exactly_lockout);
  RUN_TEST(test_zero_lockout_accepts_everything);
  RUN_TEST(test_lockout_can_be_changed);
  return UNITY_END();
}
