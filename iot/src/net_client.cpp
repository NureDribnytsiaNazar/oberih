#include "net_client.h"

#include <HTTPClient.h>

#include "config.h"

#if __has_include("secrets.h")
#include "secrets.h"
#endif

namespace {
constexpr int kErrorTlsNotConfigured = -100;
constexpr int kErrorNoServerUrl = -101;
constexpr int kErrorBeginFailed = -102;
}  // namespace

void NetClient::begin(const char* device_token) {
  device_token_ = device_token;
#if defined(OBERIH_ROOT_CA)
  tls_.setCACert(OBERIH_ROOT_CA);
  tls_ready_ = true;
#elif defined(OBERIH_DEV_TLS)
  // Лише для розробки: сертифікат сервера не перевіряється.
  tls_.setInsecure();
  tls_ready_ = true;
#else
  tls_ready_ = false;
#endif
}

HttpResult NetClient::post_json(const char* path, const std::string& body) {
  if (!tls_ready_) {
    return {kErrorTlsNotConfigured, ""};
  }
  if (server_url_.empty()) {
    return {kErrorNoServerUrl, ""};
  }
  HTTPClient http;
  http.setTimeout(config::kHttpTimeoutMs);
  const std::string url = server_url_ + path;
  if (!http.begin(tls_, url.c_str())) {
    return {kErrorBeginFailed, ""};
  }
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Token", device_token_.c_str());
  const int status = http.POST(
      reinterpret_cast<uint8_t*>(const_cast<char*>(body.data())), body.size());
  HttpResult result{status, ""};
  if (status > 0) {
    result.body = http.getString().c_str();
  }
  http.end();
  return result;
}
