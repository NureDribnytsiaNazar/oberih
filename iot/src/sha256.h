// SHA-256 (FIPS 180-4) і HMAC-SHA256 (RFC 2104) без залежності від платформи.
// Власна реалізація потрібна, щоб перевірка підпису команд працювала й у
// юніт-тестах на ПК; правильність перевіряється тестовими векторами RFC 4231.
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

constexpr size_t kSha256DigestBytes = 32;

class Sha256 {
 public:
  Sha256();
  void update(const uint8_t* data, size_t length);
  void finish(uint8_t digest[kSha256DigestBytes]);

 private:
  static constexpr size_t kBlockBytes = 64;
  void process_block(const uint8_t block[kBlockBytes]);

  uint32_t state_[8];
  uint8_t buffer_[kBlockBytes];
  size_t buffer_length_ = 0;
  uint64_t total_bytes_ = 0;
};

void hmac_sha256(const uint8_t* key, size_t key_length, const uint8_t* message,
                 size_t message_length, uint8_t digest[kSha256DigestBytes]);

// Байти -> рядок малими шістнадцятковими цифрами.
std::string to_hex(const uint8_t* data, size_t length);
// Рядок hex -> байти; false, якщо довжина чи символи некоректні.
bool from_hex(const std::string& hex, uint8_t* out, size_t out_length);
// Порівняння сталого часу (час не залежить від позиції розбіжності).
bool constant_time_equal(const std::string& left, const std::string& right);
