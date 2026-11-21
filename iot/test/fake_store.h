// Підставне сховище в пам'яті для тестів (замість NVS).
// Той самий об'єкт, переданий новому буферу, імітує перезавантаження.
#pragma once

#include <cstring>
#include <map>
#include <string>
#include <vector>

#include "storage.h"

class FakeStore : public KeyValueStore {
 public:
  bool read_blob(const char* key, void* data, size_t size) override {
    auto found = blobs_.find(key);
    if (found == blobs_.end() || found->second.size() != size) {
      return false;
    }
    std::memcpy(data, found->second.data(), size);
    return true;
  }

  bool write_blob(const char* key, const void* data, size_t size) override {
    if (fail_writes) {
      return false;
    }
    const auto* bytes = static_cast<const unsigned char*>(data);
    blobs_[key].assign(bytes, bytes + size);
    return true;
  }

  bool read_u64(const char* key, uint64_t* value) override {
    auto found = numbers_.find(key);
    if (found == numbers_.end()) {
      return false;
    }
    *value = found->second;
    return true;
  }

  bool write_u64(const char* key, uint64_t value) override {
    if (fail_writes) {
      return false;
    }
    numbers_[key] = value;
    return true;
  }

  bool erase(const char* key) override {
    return blobs_.erase(key) + numbers_.erase(key) > 0;
  }

  bool fail_writes = false;

 private:
  std::map<std::string, std::vector<unsigned char>> blobs_;
  std::map<std::string, uint64_t> numbers_;
};
