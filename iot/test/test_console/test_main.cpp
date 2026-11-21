// Консоль налаштувань (заміна BLE у симуляції) та індикація (ІК-6).
#include <unity.h>

#include <string>

#include "config.h"
#include "console.h"
#include "indicators.h"

namespace {

class FakeActions : public ConsoleActions {
 public:
  bool save_settings(const NodeSettings& settings) override {
    saved = settings;
    ++saves;
    return true;
  }
  void settings_changed() override { ++changes; }
  std::string status() override { return "status\n"; }
  std::string buffer_dump() override { return "buffer\n"; }
  void set_network_enabled(bool enabled) override { network = enabled; }
  bool simulate_bounce(uint8_t channel) override {
    bounced = channel;
    return true;
  }
  std::string inject_forged_command() override { return "forged\n"; }

  NodeSettings saved{};
  int saves = 0;
  int changes = 0;
  bool network = true;
  uint8_t bounced = 0;
};

bool contains(const std::string& text, const char* part) {
  return text.find(part) != std::string::npos;
}

}  // namespace

void setUp() {}
void tearDown() {}

void test_set_and_save() {
  NodeSettings settings = default_settings();
  FakeActions actions;
  Console console(settings, actions);
  console.handle_line("set exit_delay 20");
  console.handle_line("set debounce_ms 80");
  TEST_ASSERT_EQUAL_UINT32(20, settings.exit_delay_s);
  TEST_ASSERT_EQUAL(2, actions.changes);
  TEST_ASSERT_TRUE(contains(console.handle_line("save"), "saved"));
  TEST_ASSERT_EQUAL_UINT32(80, actions.saved.debounce_ms);
}

void test_invalid_set_is_reported() {
  NodeSettings settings = default_settings();
  FakeActions actions;
  Console console(settings, actions);
  const std::string reply = console.handle_line("set debounce_ms 5");
  TEST_ASSERT_TRUE(contains(reply, "rejected"));
  TEST_ASSERT_EQUAL(0, actions.changes);
  TEST_ASSERT_TRUE(contains(console.handle_line("set exit_delay"), "usage"));
}

void test_get_and_defaults() {
  NodeSettings settings = default_settings();
  FakeActions actions;
  Console console(settings, actions);
  console.handle_line("set server_url https://demo.example");
  console.handle_line("set pir_lockout 20");
  TEST_ASSERT_TRUE(contains(console.handle_line("get"), "pir_lockout = 20"));
  console.handle_line("defaults");
  TEST_ASSERT_EQUAL_UINT32(10, settings.pir_lockout_s);
  TEST_ASSERT_EQUAL_STRING("https://demo.example", settings.server_url);
}

void test_simulation_and_network_commands() {
  NodeSettings settings = default_settings();
  FakeActions actions;
  Console console(settings, actions);
  console.handle_line("net off");
  TEST_ASSERT_FALSE(actions.network);
  console.handle_line("sim bounce 2");
  TEST_ASSERT_EQUAL(2, actions.bounced);
  TEST_ASSERT_TRUE(contains(console.handle_line("sim bounce 3"), "usage"));
  TEST_ASSERT_TRUE(contains(console.handle_line("sim badcmd"), "forged"));
  TEST_ASSERT_TRUE(contains(console.handle_line("dance"), "unknown"));
}

void test_indicator_modes() {
  IndicatorInput input{Mode::kDisarmed, false, false, 0, 100};
  IndicatorOutput out = indicator_state(input);
  TEST_ASSERT_TRUE(out.green && !out.red && !out.blue);
  input.mode = Mode::kArmedHome;
  out = indicator_state(input);
  TEST_ASSERT_TRUE(out.green && out.red);
  input.mode = Mode::kAlarm;
  out = indicator_state(input);
  TEST_ASSERT_EQUAL_UINT16(config::kAlarmToneHz, out.tone_hz);
}

void test_indicator_offline_and_restore() {
  IndicatorInput input{Mode::kArmedAway, true, false, 0, 100};
  IndicatorOutput out = indicator_state(input);
  TEST_ASSERT_TRUE(out.blue && !out.red);  // синій спалах
  TEST_ASSERT_EQUAL_UINT16(config::kNoticeToneHz, out.tone_hz);
  input.now_ms = 700;
  out = indicator_state(input);
  TEST_ASSERT_TRUE(out.red && !out.blue);  // між спалахами — колір режиму
  TEST_ASSERT_EQUAL_UINT16(0, out.tone_hz);

  IndicatorInput restored{Mode::kArmedAway, false, true, 5000, 6000};
  out = indicator_state(restored);
  TEST_ASSERT_TRUE(out.blue && out.red);
  restored.now_ms = 9000;
  TEST_ASSERT_FALSE(indicator_state(restored).blue);
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_set_and_save);
  RUN_TEST(test_invalid_set_is_reported);
  RUN_TEST(test_get_and_defaults);
  RUN_TEST(test_simulation_and_network_commands);
  RUN_TEST(test_indicator_modes);
  RUN_TEST(test_indicator_offline_and_restore);
  return UNITY_END();
}
