#include "net_client.h"

#include "config.h"

#if __has_include("secrets.h")
#include "secrets.h"
#endif

namespace {
constexpr int kErrorTlsNotConfigured = -100;
constexpr int kErrorNoServerUrl = -101;
constexpr int kErrorBeginFailed = -102;
constexpr size_t kErrorTextSize = 96;
}  // namespace

void NetClient::begin(const char* device_token) {
  device_token_ = device_token;
#if defined(OBERIH_CA_CERT)
  tls_.setCACert(OBERIH_CA_CERT);
  tls_ready_ = true;
#elif defined(OBERIH_DEV_TLS)
  // Лише для розробки: сертифікат сервера не перевіряється.
  tls_.setInsecure();
  tls_ready_ = true;
#else
  tls_ready_ = false;
#endif
  http_.setReuse(true);
  http_.setTimeout(config::kHttpTimeoutMs);
}

void NetClient::set_server_url(const char* server_url) {
  if (server_url_ != server_url) {
    disconnect();  // з'єднання з попереднім сервером більше не потрібне
  }
  server_url_ = server_url;
}

void NetClient::disconnect() { tls_.stop(); }

HttpResult NetClient::post_json(const char* path, const std::string& body) {
  if (!tls_ready_) {
    return {kErrorTlsNotConfigured, ""};
  }
  if (server_url_.empty()) {
    return {kErrorNoServerUrl, ""};
  }
  last_error_.clear();
  const uint32_t started_ms = millis();
  if (!tls_.connected()) {
    ++handshakes_;  // HTTPClient відкриє нове з'єднання з рукопожаттям
  }
  const std::string url = server_url_ + path;
  if (!http_.begin(tls_, url.c_str())) {
    return {kErrorBeginFailed, ""};
  }
  http_.addHeader("Content-Type", "application/json");
  http_.addHeader("X-Device-Token", device_token_.c_str());
  const int status = http_.POST(
      reinterpret_cast<uint8_t*>(const_cast<char*>(body.data())), body.size());
  HttpResult result{status, ""};
  if (status > 0) {
    // Тіло читається повністю, щоб з'єднання можна було використати знову.
    result.body = http_.getString().c_str();
    http_.end();  // з keep-alive з'єднання лишається відкритим
  } else {
    char text[kErrorTextSize] = {};
    const int tls_code = tls_.lastError(text, sizeof(text));
    last_error_ = std::string(HTTPClient::errorToString(status).c_str()) +
                  "; tls " + std::to_string(tls_code) + " " + text;
    http_.end();
    disconnect();  // наступна спроба почнеться з нового з'єднання
  }
  last_duration_ms_ = millis() - started_ms;
  return result;
}
