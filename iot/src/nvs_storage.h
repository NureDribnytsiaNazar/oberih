// Сховище KeyValueStore на основі NVS ESP32 (бібліотека Preferences).
#pragma once

#include <Preferences.h>

#include "storage.h"

class NvsStore : public KeyValueStore {
 public:
  // Відкриває простір імен NVS; false — NVS недоступна.
  bool begin(const char* name_space);

  bool read_blob(const char* key, void* data, size_t size) override;
  bool write_blob(const char* key, const void* data, size_t size) override;
  bool read_u64(const char* key, uint64_t* value) override;
  bool write_u64(const char* key, uint64_t value) override;
  bool erase(const char* key) override;

 private:
  Preferences prefs_;
  bool ready_ = false;
};
