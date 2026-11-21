// ІК-7: SHA-256, HMAC і перевірка команд сервера.
#include <unity.h>

#include <cstring>

#include "command_verifier.h"
#include "sha256.h"

namespace {

// Вектор, обчислений сервером (app/services/commands.py: sign) для ключа
// 00 01 .. 1f — підтверджує, що вузол і сервер підписують однаково.
constexpr const char* kNodeId = "6f1c2a5e-0000-4000-8000-000000000001";
constexpr const char* kServerSignature =
    "fc14a6ed75d104dea0a27c6160375e7712182b82f65706f2ca3635388f85dc01";
constexpr int64_t kIssuedAt = 1763700000;
constexpr uint64_t kNonce = 1763700000123ULL;

struct Fixture {
  uint8_t key[32];
  Command command;
  Fixture() {
    for (uint8_t i = 0; i < 32; ++i) {
      key[i] = i;
    }
    command.id = "cmd-1";
    command.type = "disarm";
    command.payload = "{\"mode\":\"disarmed\"}";
    command.nonce = kNonce;
    command.issued_at = kIssuedAt;
    command.signature = kServerSignature;
  }
};

std::string hmac_hex(const std::string& key, const std::string& message) {
  uint8_t digest[kSha256DigestBytes];
  hmac_sha256(reinterpret_cast<const uint8_t*>(key.data()), key.size(),
              reinterpret_cast<const uint8_t*>(message.data()), message.size(),
              digest);
  return to_hex(digest, sizeof(digest));
}

}  // namespace

void setUp() {}
void tearDown() {}

void test_sha256_known_vectors() {
  uint8_t digest[kSha256DigestBytes];
  Sha256 empty;
  empty.finish(digest);
  TEST_ASSERT_EQUAL_STRING(
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      to_hex(digest, sizeof(digest)).c_str());
  Sha256 abc;
  abc.update(reinterpret_cast<const uint8_t*>("abc"), 3);
  abc.finish(digest);
  TEST_ASSERT_EQUAL_STRING(
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
      to_hex(digest, sizeof(digest)).c_str());
}

void test_hmac_rfc4231_case2() {
  TEST_ASSERT_EQUAL_STRING(
      "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843",
      hmac_hex("Jefe", "what do ya want for nothing?").c_str());
}

void test_valid_server_signature_is_accepted() {
  Fixture f;
  CommandVerifier verifier(f.key, kNodeId);
  TEST_ASSERT_EQUAL(VerifyResult::kAccepted,
                    verifier.verify(f.command, true, kIssuedAt + 5, 0));
}

void test_changed_payload_is_rejected() {
  Fixture f;
  CommandVerifier verifier(f.key, kNodeId);
  f.command.payload = "{\"mode\":\"armed_away\"}";
  TEST_ASSERT_EQUAL(VerifyResult::kBadSignature,
                    verifier.verify(f.command, true, kIssuedAt, 0));
}

void test_other_node_cannot_use_command() {
  Fixture f;
  CommandVerifier verifier(f.key, "another-node");
  TEST_ASSERT_EQUAL(VerifyResult::kBadSignature,
                    verifier.verify(f.command, true, kIssuedAt, 0));
}

void test_expired_timestamp_is_rejected() {
  Fixture f;
  CommandVerifier verifier(f.key, kNodeId);
  TEST_ASSERT_EQUAL(VerifyResult::kAccepted,
                    verifier.verify(f.command, true, kIssuedAt + 60, 0));
  TEST_ASSERT_EQUAL(VerifyResult::kExpired,
                    verifier.verify(f.command, true, kIssuedAt + 61, 0));
  TEST_ASSERT_EQUAL(VerifyResult::kExpired,
                    verifier.verify(f.command, true, kIssuedAt - 61, 0));
}

void test_unsynced_clock_is_not_trusted() {
  Fixture f;
  CommandVerifier verifier(f.key, kNodeId);
  TEST_ASSERT_EQUAL(VerifyResult::kClockNotSynced,
                    verifier.verify(f.command, false, kIssuedAt, 0));
}

void test_repeated_nonce_is_rejected() {
  Fixture f;
  CommandVerifier verifier(f.key, kNodeId);
  TEST_ASSERT_EQUAL(VerifyResult::kReplay,
                    verifier.verify(f.command, true, kIssuedAt, kNonce));
  TEST_ASSERT_EQUAL(VerifyResult::kReplay,
                    verifier.verify(f.command, true, kIssuedAt, kNonce + 1));
}

void test_command_target_mode() {
  Mode mode = Mode::kAlarm;
  TEST_ASSERT_TRUE(command_target_mode("arm_away", "exit_delay", &mode));
  TEST_ASSERT_EQUAL(Mode::kExitDelay, mode);
  TEST_ASSERT_TRUE(command_target_mode("disarm", "disarmed", &mode));
  TEST_ASSERT_FALSE(command_target_mode("disarm", "armed_home", &mode));
  TEST_ASSERT_FALSE(command_target_mode("set_config", "disarmed", &mode));
}

void test_hex_helpers() {
  uint8_t bytes[2];
  TEST_ASSERT_TRUE(from_hex("0aFf", bytes, 2));
  TEST_ASSERT_EQUAL_HEX8(0x0A, bytes[0]);
  TEST_ASSERT_EQUAL_HEX8(0xFF, bytes[1]);
  TEST_ASSERT_FALSE(from_hex("0g00", bytes, 2));
  TEST_ASSERT_FALSE(from_hex("00", bytes, 2));
  TEST_ASSERT_TRUE(constant_time_equal("abc", "abc"));
  TEST_ASSERT_FALSE(constant_time_equal("abc", "abd"));
}

int main() {
  UNITY_BEGIN();
  RUN_TEST(test_sha256_known_vectors);
  RUN_TEST(test_hmac_rfc4231_case2);
  RUN_TEST(test_valid_server_signature_is_accepted);
  RUN_TEST(test_changed_payload_is_rejected);
  RUN_TEST(test_other_node_cannot_use_command);
  RUN_TEST(test_expired_timestamp_is_rejected);
  RUN_TEST(test_unsynced_clock_is_not_trusted);
  RUN_TEST(test_repeated_nonce_is_rejected);
  RUN_TEST(test_command_target_mode);
  RUN_TEST(test_hex_helpers);
  return UNITY_END();
}
