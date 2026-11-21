#include "sha256.h"

#include <cstring>

namespace {

constexpr uint32_t kRoundConstants[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
    0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
    0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
    0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
    0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
    0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
};

constexpr uint32_t kInitialState[8] = {
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
};

constexpr size_t kHmacBlockBytes = 64;
constexpr uint8_t kInnerPad = 0x36;
constexpr uint8_t kOuterPad = 0x5c;
constexpr const char* kHexDigits = "0123456789abcdef";

uint32_t rotate_right(uint32_t value, uint32_t bits) {
  return (value >> bits) | (value << (32 - bits));
}

int hex_value(char symbol) {
  if (symbol >= '0' && symbol <= '9') {
    return symbol - '0';
  }
  if (symbol >= 'a' && symbol <= 'f') {
    return symbol - 'a' + 10;
  }
  if (symbol >= 'A' && symbol <= 'F') {
    return symbol - 'A' + 10;
  }
  return -1;
}

}  // namespace

Sha256::Sha256() { std::memcpy(state_, kInitialState, sizeof(state_)); }

void Sha256::update(const uint8_t* data, size_t length) {
  total_bytes_ += length;
  while (length > 0) {
    const size_t room = kBlockBytes - buffer_length_;
    const size_t chunk = length < room ? length : room;
    std::memcpy(buffer_ + buffer_length_, data, chunk);
    buffer_length_ += chunk;
    data += chunk;
    length -= chunk;
    if (buffer_length_ == kBlockBytes) {
      process_block(buffer_);
      buffer_length_ = 0;
    }
  }
}

void Sha256::finish(uint8_t digest[kSha256DigestBytes]) {
  const uint64_t total_bits = total_bytes_ * 8;
  const uint8_t terminator = 0x80;
  update(&terminator, 1);
  const uint8_t zero = 0;
  // Доповнюємо нулями, доки до кінця блоку не лишиться 8 байтів довжини.
  while (buffer_length_ != kBlockBytes - 8) {
    update(&zero, 1);
  }
  uint8_t length_bytes[8];
  for (int i = 0; i < 8; ++i) {
    length_bytes[i] = static_cast<uint8_t>(total_bits >> (56 - 8 * i));
  }
  update(length_bytes, sizeof(length_bytes));
  for (int i = 0; i < 8; ++i) {
    digest[4 * i] = static_cast<uint8_t>(state_[i] >> 24);
    digest[4 * i + 1] = static_cast<uint8_t>(state_[i] >> 16);
    digest[4 * i + 2] = static_cast<uint8_t>(state_[i] >> 8);
    digest[4 * i + 3] = static_cast<uint8_t>(state_[i]);
  }
}

void Sha256::process_block(const uint8_t block[kBlockBytes]) {
  uint32_t w[64];
  for (int i = 0; i < 16; ++i) {
    w[i] = (static_cast<uint32_t>(block[4 * i]) << 24) |
           (static_cast<uint32_t>(block[4 * i + 1]) << 16) |
           (static_cast<uint32_t>(block[4 * i + 2]) << 8) |
           static_cast<uint32_t>(block[4 * i + 3]);
  }
  for (int i = 16; i < 64; ++i) {
    const uint32_t s0 = rotate_right(w[i - 15], 7) ^
                        rotate_right(w[i - 15], 18) ^ (w[i - 15] >> 3);
    const uint32_t s1 = rotate_right(w[i - 2], 17) ^
                        rotate_right(w[i - 2], 19) ^ (w[i - 2] >> 10);
    w[i] = w[i - 16] + s0 + w[i - 7] + s1;
  }
  uint32_t a = state_[0], b = state_[1], c = state_[2], d = state_[3];
  uint32_t e = state_[4], f = state_[5], g = state_[6], h = state_[7];
  for (int i = 0; i < 64; ++i) {
    const uint32_t s1 =
        rotate_right(e, 6) ^ rotate_right(e, 11) ^ rotate_right(e, 25);
    const uint32_t choice = (e & f) ^ (~e & g);
    const uint32_t temp1 = h + s1 + choice + kRoundConstants[i] + w[i];
    const uint32_t s0 =
        rotate_right(a, 2) ^ rotate_right(a, 13) ^ rotate_right(a, 22);
    const uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
    const uint32_t temp2 = s0 + majority;
    h = g;
    g = f;
    f = e;
    e = d + temp1;
    d = c;
    c = b;
    b = a;
    a = temp1 + temp2;
  }
  state_[0] += a;
  state_[1] += b;
  state_[2] += c;
  state_[3] += d;
  state_[4] += e;
  state_[5] += f;
  state_[6] += g;
  state_[7] += h;
}

void hmac_sha256(const uint8_t* key, size_t key_length, const uint8_t* message,
                 size_t message_length, uint8_t digest[kSha256DigestBytes]) {
  uint8_t block_key[kHmacBlockBytes] = {};
  if (key_length > kHmacBlockBytes) {
    Sha256 key_hash;
    key_hash.update(key, key_length);
    key_hash.finish(block_key);
  } else {
    std::memcpy(block_key, key, key_length);
  }
  uint8_t pad[kHmacBlockBytes];
  for (size_t i = 0; i < kHmacBlockBytes; ++i) {
    pad[i] = block_key[i] ^ kInnerPad;
  }
  uint8_t inner_digest[kSha256DigestBytes];
  Sha256 inner;
  inner.update(pad, sizeof(pad));
  inner.update(message, message_length);
  inner.finish(inner_digest);

  for (size_t i = 0; i < kHmacBlockBytes; ++i) {
    pad[i] = block_key[i] ^ kOuterPad;
  }
  Sha256 outer;
  outer.update(pad, sizeof(pad));
  outer.update(inner_digest, sizeof(inner_digest));
  outer.finish(digest);
}

std::string to_hex(const uint8_t* data, size_t length) {
  std::string hex;
  hex.reserve(length * 2);
  for (size_t i = 0; i < length; ++i) {
    hex.push_back(kHexDigits[data[i] >> 4]);
    hex.push_back(kHexDigits[data[i] & 0x0F]);
  }
  return hex;
}

bool from_hex(const std::string& hex, uint8_t* out, size_t out_length) {
  if (hex.size() != out_length * 2) {
    return false;
  }
  for (size_t i = 0; i < out_length; ++i) {
    const int high = hex_value(hex[2 * i]);
    const int low = hex_value(hex[2 * i + 1]);
    if (high < 0 || low < 0) {
      return false;
    }
    out[i] = static_cast<uint8_t>((high << 4) | low);
  }
  return true;
}

bool constant_time_equal(const std::string& left, const std::string& right) {
  if (left.size() != right.size()) {
    return false;  // довжина підпису не секретна
  }
  uint8_t difference = 0;
  for (size_t i = 0; i < left.size(); ++i) {
    difference |= static_cast<uint8_t>(left[i] ^ right[i]);
  }
  return difference == 0;
}
