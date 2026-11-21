// Консоль налаштувань через Serial (заміна BLE у симуляції, ЗЛ-1).
// Розбір команд — чистий код; дії з обладнанням і мережею виконує
// реалізація ConsoleActions (node_app.cpp, у тестах — підставна).
//
// Команди: help, get, set <ключ> <значення>, save, defaults, status,
// buffer, net on|off, sim bounce <канал>, sim badcmd.
#pragma once

#include <cstdint>
#include <string>

#include "settings.h"

class ConsoleActions {
 public:
  virtual ~ConsoleActions() = default;
  virtual bool save_settings(const NodeSettings& settings) = 0;
  virtual void settings_changed() = 0;  // застосувати до фільтрів і автомата
  virtual std::string status() = 0;
  virtual std::string buffer_dump() = 0;
  virtual void set_network_enabled(bool enabled) = 0;
  virtual bool simulate_bounce(uint8_t channel) = 0;
  virtual std::string inject_forged_command() = 0;
};

class Console {
 public:
  Console(NodeSettings& settings, ConsoleActions& actions);

  // Виконує один рядок і повертає відповідь для виведення.
  std::string handle_line(const std::string& line);

 private:
  std::string handle_set(const std::string& key, const std::string& value);
  std::string handle_sim(const std::string& what, const std::string& argument);

  NodeSettings& settings_;
  ConsoleActions& actions_;
};
