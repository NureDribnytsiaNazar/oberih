// Енергонезалежне сховище «ключ — значення».
// На ESP32 його реалізує NVS (nvs_storage.h), у тестах — підставне сховище
// в пам'яті. Так логіка буфера й налаштувань не залежить від Arduino API.
#pragma once

#include <cstddef>
#include <cstdint>

class KeyValueStore {
 public:
  virtual ~KeyValueStore() = default;

  // false — ключа немає або розмір збереженого значення інший.
  virtual bool read_blob(const char* key, void* data, size_t size) = 0;
  virtual bool write_blob(const char* key, const void* data, size_t size) = 0;
  virtual bool read_u64(const char* key, uint64_t* value) = 0;
  virtual bool write_u64(const char* key, uint64_t value) = 0;
  virtual bool erase(const char* key) = 0;
};
