// ІК-8: налаштування — межі, значення за замовчуванням, конфігурація сервера.
#include <unity.h>

#include "../fake_store.h"
#include "config.h"
#include "settings.h"

void setUp() {}
void tearDown() {}

void test_defaults_match_vision_and_scope() {
  const NodeSettings settings = default_settings();
  TEST_ASSERT_EQUAL_UINT32(30, settings.exit_delay_s);
  TEST_ASSERT_EQUAL_UINT32(30, settings.entry_delay_s);
  TEST_ASSERT_EQUAL_UINT32(30, settings.poll_interval_s);
  TEST_ASSERT_EQUAL_UINT32(50, settings.debounce_ms);
  TEST_ASSERT_EQUAL_UINT32(10, settings.pir_lockout_s);
  TEST_ASSERT_EQUAL_UINT32(0, settings.config_version);
  TEST_ASSERT_TRUE(settings_valid(settings));
}

void test_set_within_bounds() {
  NodeSettings settings = default_settings();
  TEST_ASSERT_EQUAL(SettingResult::kOk,
                    set_setting(settings, "exit_delay", "20"));
  TEST_ASSERT_EQUAL(SettingResult::kOk,
                    set_setting(settings, "debounce_ms", "10"));
  TEST_ASSERT_EQUAL(SettingResult::kOk,
                    set_setting(settings, "debounce_ms", "1000"));
  TEST_ASSERT_EQUAL_UINT32(20, settings.exit_delay_s);
  TEST_ASSERT_EQUAL_UINT32(1000, settings.debounce_ms);
}

void test_invalid_values_are_rejected_without_change() {
  NodeSettings settings = default_settings();
  TEST_ASSERT_EQUAL(SettingResult::kOutOfRange,
                    set_setting(settings, "debounce_ms", "9"));
  TEST_ASSERT_EQUAL(SettingResult::kOutOfRange,
                    set_setting(settings, "poll_interval", "4"));
  TEST_ASSERT_EQUAL(SettingResult::kInvalidNumber,
                    set_setting(settings, "exit_delay", "-1"));
  TEST_ASSERT_EQUAL(SettingResult::kInvalidNumber,
                    set_setting(settings, "exit_delay", "2a"));
  TEST_ASSERT_EQUAL(SettingResult::kUnknownKey,
                    set_setting(settings, "volume", "3"));
  TEST_ASSERT_EQUAL(SettingResult::kInvalidUrl,
                    set_setting(settings, "server_url", "http://plain"));
  TEST_ASSERT_EQUAL_UINT32(50, settings.debounce_ms);
  TEST_ASSERT_EQUAL_UINT32(30, settings.exit_delay_s);
}

void test_server_config_applies_only_newer_version() {
  NodeSettings settings = default_settings();
  NodeSettings incoming = default_settings();
  incoming.debounce_ms = 80;
  incoming.config_version = 2;
  TEST_ASSERT_EQUAL(ConfigApplyResult::kApplied,
                    apply_server_config(settings, incoming));
  TEST_ASSERT_EQUAL_UINT32(80, settings.debounce_ms);

  incoming.debounce_ms = 90;  // та сама версія — не застосовується
  TEST_ASSERT_EQUAL(ConfigApplyResult::kStale,
                    apply_server_config(settings, incoming));
  TEST_ASSERT_EQUAL_UINT32(80, settings.debounce_ms);
}

void test_invalid_server_config_is_rejected_entirely() {
  NodeSettings settings = default_settings();
  NodeSettings incoming = default_settings();
  incoming.config_version = 5;
  incoming.exit_delay_s = 20;
  incoming.debounce_ms = 5000;
  TEST_ASSERT_EQUAL(ConfigApplyResult::kInvalid,
                    apply_server_config(settings, incoming));
  TEST_ASSERT_EQUAL_UINT32(30, settings.exit_delay_s);
  TEST_ASSERT_EQUAL_UINT32(0, settings.config_version);
}

void test_settings_persist_in_store() {
  FakeStore store;
  NodeSettings settings = default_settings();
  set_setting(settings, "pir_lockout", "15");
  TEST_ASSERT_TRUE(save_settings(store, settings));
  NodeSettings loaded{};
  TEST_ASSERT_TRUE(load_settings(store, &loaded));
  TEST_ASSERT_EQUAL_UINT32(15, loaded.pir_lockout_s);
}

void test_missing_store_falls_back() {
  FakeStore store;
  NodeSettings loaded{};
  TEST_ASSERT_FALSE(load_settings(store, &loaded));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_defaults_match_vision_and_scope);
  RUN_TEST(test_set_within_bounds);
  RUN_TEST(test_invalid_values_are_rejected_without_change);
  RUN_TEST(test_server_config_applies_only_newer_version);
  RUN_TEST(test_invalid_server_config_is_rejected_entirely);
  RUN_TEST(test_settings_persist_in_store);
  RUN_TEST(test_missing_store_falls_back);
  return UNITY_END();
}
