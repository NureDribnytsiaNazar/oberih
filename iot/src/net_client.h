// HTTPS-клієнт вузла: POST JSON на сервер із токеном пристрою.
// TLS: сертифікат-якір OBERIH_CA_CERT із secrets.h (setCACert); режим
// без перевірки сертифіката (setInsecure) — лише з прапорцем OBERIH_DEV_TLS.
// З'єднання TLS тримається відкритим між запитами (HTTP keep-alive): повне
// рукопожаття дороге (у симуляторі Wokwi — секунди), тому воно виконується
// лише для першого запиту й після обриву з'єднання.
#pragma once

#include <HTTPClient.h>
#include <WiFiClientSecure.h>

#include <string>

struct HttpResult {
  int status;  // HTTP-код або від'ємний код помилки з'єднання
  std::string body;
};

class NetClient {
 public:
  void begin(const char* device_token);
  void set_server_url(const char* server_url);

  HttpResult post_json(const char* path, const std::string& body);

  // Закриває з'єднання (вимкнення мережі, зміна адреси сервера).
  void disconnect();

  // Чи налаштовано TLS (є сертифікат-якір або режим розробки).
  bool tls_ready() const { return tls_ready_; }
  // Опис останньої помилки з'єднання (текст mbedTLS) і тривалість запиту.
  const std::string& last_error() const { return last_error_; }
  uint32_t last_duration_ms() const { return last_duration_ms_; }
  // Скільки разів відкривалося нове з'єднання TLS (повне рукопожаття).
  uint32_t handshakes() const { return handshakes_; }

 private:
  WiFiClientSecure tls_;
  // Один об'єкт на весь час роботи: деструктор HTTPClient закриває з'єднання.
  HTTPClient http_;
  std::string server_url_;
  std::string device_token_;
  bool tls_ready_ = false;
  std::string last_error_;
  uint32_t last_duration_ms_ = 0;
  uint32_t handshakes_ = 0;
};
