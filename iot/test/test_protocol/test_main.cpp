// Формат обміну із сервером: пакет подій, heartbeat, команди.
#include <unity.h>

#include <string>

#include "protocol.h"

namespace {

// Відповідь у форматі HeartbeatOut сервера (поля, які читає вузол).
constexpr const char* kHeartbeatReply = R"({
  "server_time": "2025-11-21T04:40:00Z",
  "poll_interval_s": 30,
  "facility_mode": "armed_home",
  "server_epoch": 1763700000,
  "last_seq": 17,
  "config": {"exit_delay_s": 20, "entry_delay_s": 30, "poll_interval_s": 30,
             "debounce_ms": 80, "pir_lockout_s": 10, "config_version": 3},
  "commands": [
    {"id": "c1", "type": "arm_home", "payload": "{\"mode\":\"armed_home\"}",
     "nonce": 1763700000123, "issued_at": 1763700000,
     "expires_at": 1763700060, "signature": "ab"},
    {"id": "broken", "type": "disarm"}
  ]
})";

bool contains(const std::string& text, const char* part) {
  return text.find(part) != std::string::npos;
}

}  // namespace

void setUp() {}
void tearDown() {}

void test_format_utc() {
  TEST_ASSERT_EQUAL_STRING("1970-01-01T00:00:00Z", format_utc(0).c_str());
  TEST_ASSERT_EQUAL_STRING("2025-11-21T04:40:00Z",
                           format_utc(1763700000).c_str());
  TEST_ASSERT_EQUAL_STRING("2000-02-29T00:00:00Z",
                           format_utc(951782400).c_str());
}

void test_events_batch_json() {
  BufferedEvent events[2] = {
      {5, 1763700000, 0, 1, EventType::kOpened, 0},
      {6, 1763700001, 0, 3, EventType::kMotion, EventBuffer::kFlagApproxTime},
  };
  const std::string body = build_events_json(events, 2);
  TEST_ASSERT_TRUE(contains(
      body, R"({"channel":1,"event_type":"opened","seq":5,)"
            R"("occurred_at":"2025-11-21T04:40:00Z"})"));
  TEST_ASSERT_TRUE(contains(body, R"("payload":{"approx_time":true})"));
}

void test_heartbeat_json() {
  HeartbeatReport report{"0.4.0", Mode::kArmedAway, 3, 2, {"c1", "c2"}};
  const std::string body = build_heartbeat_json(report);
  TEST_ASSERT_TRUE(contains(body, R"("mode":"armed_away")"));
  TEST_ASSERT_TRUE(contains(body, R"("buffer_depth":2)"));
  TEST_ASSERT_TRUE(contains(body, R"("acked_command_ids":["c1","c2"])"));
}

void test_parse_heartbeat_reply() {
  HeartbeatReply reply;
  TEST_ASSERT_TRUE(parse_heartbeat(kHeartbeatReply, &reply));
  TEST_ASSERT_EQUAL_INT64(1763700000, reply.server_epoch);
  TEST_ASSERT_EQUAL_STRING("armed_home", reply.facility_mode.c_str());
  TEST_ASSERT_EQUAL_UINT64(17, reply.last_seq);
  TEST_ASSERT_TRUE(reply.has_config);
  TEST_ASSERT_EQUAL_UINT32(80, reply.config.debounce_ms);
  TEST_ASSERT_EQUAL_UINT32(3, reply.config.config_version);
  // Некоректна команда пропускається, решта розбирається.
  TEST_ASSERT_EQUAL(1, reply.commands.size());
  TEST_ASSERT_EQUAL_UINT64(1763700000123ULL, reply.commands[0].nonce);
  TEST_ASSERT_EQUAL_STRING("{\"mode\":\"armed_home\"}",
                           reply.commands[0].payload.c_str());
}

void test_old_server_reply_without_extensions() {
  HeartbeatReply reply;
  const char* old_reply =
      R"({"server_time":"x","poll_interval_s":30,"facility_mode":"disarmed"})";
  // Без server_epoch вузол не може синхронізувати годинник.
  TEST_ASSERT_FALSE(parse_heartbeat(old_reply, &reply));
  TEST_ASSERT_FALSE(parse_heartbeat("not json", &reply));
}

void test_command_payloads() {
  std::string mode;
  TEST_ASSERT_TRUE(parse_mode_payload(R"({"mode":"disarmed"})", &mode));
  TEST_ASSERT_EQUAL_STRING("disarmed", mode.c_str());
  TEST_ASSERT_FALSE(parse_mode_payload("{}", &mode));
  NodeSettings config{};
  TEST_ASSERT_TRUE(parse_config_payload(
      R"({"config_version":4,"debounce_ms":60,"entry_delay_s":30,)"
      R"("exit_delay_s":15,"pir_lockout_s":5,"poll_interval_s":30})",
      &config));
  TEST_ASSERT_EQUAL_UINT32(15, config.exit_delay_s);
  TEST_ASSERT_FALSE(parse_config_payload(R"({"debounce_ms":60})", &config));
}

void test_events_result() {
  uint32_t accepted = 0;
  uint32_t duplicates = 0;
  TEST_ASSERT_TRUE(parse_events_result(
      R"({"accepted":1,"duplicates":2,"last_seq":3,"results":[]})", &accepted,
      &duplicates));
  TEST_ASSERT_EQUAL_UINT32(1, accepted);
  TEST_ASSERT_EQUAL_UINT32(2, duplicates);
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_format_utc);
  RUN_TEST(test_events_batch_json);
  RUN_TEST(test_heartbeat_json);
  RUN_TEST(test_parse_heartbeat_reply);
  RUN_TEST(test_old_server_reply_without_extensions);
  RUN_TEST(test_command_payloads);
  RUN_TEST(test_events_result);
  return UNITY_END();
}
