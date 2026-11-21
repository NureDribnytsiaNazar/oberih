#include "nvs_storage.h"

bool NvsStore::begin(const char* name_space) {
  ready_ = prefs_.begin(name_space, false);
  return ready_;
}

bool NvsStore::read_blob(const char* key, void* data, size_t size) {
  if (!ready_ || !prefs_.isKey(key) || prefs_.getBytesLength(key) != size) {
    return false;
  }
  return prefs_.getBytes(key, data, size) == size;
}

bool NvsStore::write_blob(const char* key, const void* data, size_t size) {
  return ready_ && prefs_.putBytes(key, data, size) == size;
}

bool NvsStore::read_u64(const char* key, uint64_t* value) {
  if (!ready_ || !prefs_.isKey(key)) {
    return false;
  }
  *value = prefs_.getULong64(key, 0);
  return true;
}

bool NvsStore::write_u64(const char* key, uint64_t value) {
  return ready_ && prefs_.putULong64(key, value) == sizeof(value);
}

bool NvsStore::erase(const char* key) { return ready_ && prefs_.remove(key); }
