// ІК-1: локальний автомат режимів (ті самі переходи, що на сервері).
#include <unity.h>

#include "mode_machine.h"

namespace {

constexpr Delays kDelays{30, 20};
constexpr Delays kNoDelays{0, 0};
constexpr Mode kAllModes[] = {Mode::kDisarmed,  Mode::kExitDelay,
                              Mode::kArmedAway, Mode::kArmedHome,
                              Mode::kEntryDelay, Mode::kAlarm};

}  // namespace

void setUp() {}
void tearDown() {}

void test_arm_away_goes_through_exit_delay() {
  ModeMachine machine;
  TEST_ASSERT_TRUE(machine.apply(Trigger::kArmAway, kDelays, 0));
  TEST_ASSERT_EQUAL(Mode::kExitDelay, machine.mode());
  TEST_ASSERT_FALSE(machine.tick(kDelays, 29999));
  TEST_ASSERT_TRUE(machine.tick(kDelays, 30000));
  TEST_ASSERT_EQUAL(Mode::kArmedAway, machine.mode());
}

void test_arm_home_is_immediate() {
  ModeMachine machine;
  TEST_ASSERT_TRUE(machine.apply(Trigger::kArmHome, kDelays, 0));
  TEST_ASSERT_EQUAL(Mode::kArmedHome, machine.mode());
}

void test_intrusion_entry_delay_then_alarm() {
  ModeMachine machine(Mode::kArmedAway);
  TEST_ASSERT_TRUE(machine.on_sensor_trigger(
      SensorKind::kReed, ZoneKind::kPerimeter, kDelays, 1000));
  TEST_ASSERT_EQUAL(Mode::kEntryDelay, machine.mode());
  TEST_ASSERT_FALSE(machine.tick(kDelays, 20999));
  TEST_ASSERT_TRUE(machine.tick(kDelays, 21000));
  TEST_ASSERT_EQUAL(Mode::kAlarm, machine.mode());
}

void test_disarm_from_every_mode_except_disarmed() {
  for (Mode mode : kAllModes) {
    ModeMachine machine(mode);
    const bool allowed = machine.apply(Trigger::kDisarm, kDelays, 0);
    TEST_ASSERT_EQUAL(mode != Mode::kDisarmed, allowed);
    TEST_ASSERT_EQUAL(Mode::kDisarmed, machine.mode());
  }
}

void test_zero_delays_skip_delay_states() {
  ModeMachine machine;
  machine.apply(Trigger::kArmAway, kNoDelays, 0);
  TEST_ASSERT_EQUAL(Mode::kArmedAway, machine.mode());
  machine.on_sensor_trigger(SensorKind::kPir, ZoneKind::kInterior, kNoDelays,
                            10);
  TEST_ASSERT_EQUAL(Mode::kAlarm, machine.mode());
}

void test_tamper_alarms_from_every_mode() {
  for (Mode mode : kAllModes) {
    ModeMachine machine(mode);
    machine.on_sensor_trigger(SensorKind::kTamper, ZoneKind::kAlwaysOn,
                              kDelays, 0);
    TEST_ASSERT_EQUAL(Mode::kAlarm, machine.mode());
  }
}

void test_always_on_zone_alarms_when_disarmed() {
  ModeMachine machine;
  TEST_ASSERT_TRUE(machine.on_sensor_trigger(
      SensorKind::kReed, ZoneKind::kAlwaysOn, kDelays, 0));
  TEST_ASSERT_EQUAL(Mode::kAlarm, machine.mode());
}

void test_home_mode_ignores_interior_and_pir() {
  ModeMachine machine(Mode::kArmedHome);
  TEST_ASSERT_FALSE(machine.on_sensor_trigger(
      SensorKind::kPir, ZoneKind::kInterior, kDelays, 0));
  TEST_ASSERT_FALSE(machine.on_sensor_trigger(
      SensorKind::kReed, ZoneKind::kInterior, kDelays, 0));
  TEST_ASSERT_EQUAL(Mode::kArmedHome, machine.mode());
  TEST_ASSERT_TRUE(machine.on_sensor_trigger(
      SensorKind::kReed, ZoneKind::kPerimeter, kDelays, 0));
  TEST_ASSERT_EQUAL(Mode::kEntryDelay, machine.mode());
}

void test_sensors_ignored_when_disarmed_or_exit_delay() {
  ModeMachine disarmed;
  TEST_ASSERT_FALSE(disarmed.on_sensor_trigger(
      SensorKind::kReed, ZoneKind::kPerimeter, kDelays, 0));
  ModeMachine leaving(Mode::kExitDelay);
  TEST_ASSERT_FALSE(leaving.on_sensor_trigger(
      SensorKind::kPir, ZoneKind::kInterior, kDelays, 0));
  TEST_ASSERT_EQUAL(Mode::kExitDelay, leaving.mode());
}

void test_invalid_transitions_are_rejected() {
  Mode out = Mode::kDisarmed;
  TEST_ASSERT_FALSE(next_mode(Mode::kAlarm, Trigger::kArmAway, 30, &out));
  TEST_ASSERT_FALSE(next_mode(Mode::kDisarmed, Trigger::kIntrusion, 30, &out));
  TEST_ASSERT_FALSE(
      next_mode(Mode::kArmedAway, Trigger::kExitDelayExpired, 30, &out));
  ModeMachine machine(Mode::kArmedHome);
  TEST_ASSERT_FALSE(machine.apply(Trigger::kArmAway, kDelays, 0));
  TEST_ASSERT_EQUAL(Mode::kArmedHome, machine.mode());
}

void test_force_sets_server_mode() {
  ModeMachine machine(Mode::kAlarm);
  machine.force(Mode::kExitDelay, 500);
  TEST_ASSERT_EQUAL(Mode::kExitDelay, machine.mode());
  TEST_ASSERT_TRUE(machine.tick(kDelays, 30500));
  TEST_ASSERT_EQUAL(Mode::kArmedAway, machine.mode());
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_arm_away_goes_through_exit_delay);
  RUN_TEST(test_arm_home_is_immediate);
  RUN_TEST(test_intrusion_entry_delay_then_alarm);
  RUN_TEST(test_disarm_from_every_mode_except_disarmed);
  RUN_TEST(test_zero_delays_skip_delay_states);
  RUN_TEST(test_tamper_alarms_from_every_mode);
  RUN_TEST(test_always_on_zone_alarms_when_disarmed);
  RUN_TEST(test_home_mode_ignores_interior_and_pir);
  RUN_TEST(test_sensors_ignored_when_disarmed_or_exit_delay);
  RUN_TEST(test_invalid_transitions_are_rejected);
  RUN_TEST(test_force_sets_server_mode);
  return UNITY_END();
}
