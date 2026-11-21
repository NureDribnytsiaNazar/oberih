// HTTPS-клієнт вузла: POST JSON на сервер із токеном пристрою.
// TLS: кореневий сертифікат OBERIH_ROOT_CA із secrets.h (setCACert); режим
// без перевірки сертифіката (setInsecure) — лише з прапорцем OBERIH_DEV_TLS.
#pragma once

#include <WiFiClientSecure.h>

#include <string>

struct HttpResult {
  int status;  // HTTP-код або від'ємний код помилки з'єднання
  std::string body;
};

class NetClient {
 public:
  void begin(const char* device_token);
  void set_server_url(const char* server_url) { server_url_ = server_url; }

  HttpResult post_json(const char* path, const std::string& body);

  // Чи налаштовано TLS (є кореневий сертифікат або режим розробки).
  bool tls_ready() const { return tls_ready_; }

 private:
  WiFiClientSecure tls_;
  std::string server_url_;
  std::string device_token_;
  bool tls_ready_ = false;
};
