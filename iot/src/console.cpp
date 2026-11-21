#include "console.h"

#include <cstdlib>
#include <cstring>
#include <sstream>
#include <vector>

#include "config.h"

namespace {

constexpr const char* kHelp =
    "commands:\n"
    "  get                      current settings\n"
    "  set <key> <value>        exit_delay, entry_delay, poll_interval,\n"
    "                           debounce_ms, pir_lockout, server_url\n"
    "  save                     store settings in NVS\n"
    "  defaults                 restore default settings (then save)\n"
    "  status                   mode, connection, clock, buffer\n"
    "  buffer                   events waiting to be sent\n"
    "  net on|off               enable or disable networking\n"
    "  sim bounce <channel>     simulate contact bounce on reed 1 or 2\n"
    "  sim badcmd               feed a command with a forged signature\n";

std::vector<std::string> split_words(const std::string& line) {
  std::istringstream stream(line);
  std::vector<std::string> words;
  std::string word;
  while (stream >> word) {
    words.push_back(word);
  }
  return words;
}

std::string word_at(const std::vector<std::string>& words, size_t index) {
  return index < words.size() ? words[index] : std::string();
}

}  // namespace

Console::Console(NodeSettings& settings, ConsoleActions& actions)
    : settings_(settings), actions_(actions) {}

std::string Console::handle_line(const std::string& line) {
  const std::vector<std::string> words = split_words(line);
  if (words.empty()) {
    return "";
  }
  const std::string& command = words[0];
  if (command == "help") {
    return kHelp;
  }
  if (command == "get") {
    return describe_settings(settings_);
  }
  if (command == "set") {
    return handle_set(word_at(words, 1), word_at(words, 2));
  }
  if (command == "save") {
    return actions_.save_settings(settings_) ? "saved\n"
                                             : "error: NVS write failed\n";
  }
  if (command == "defaults") {
    NodeSettings defaults = default_settings();
    // Адреса сервера не скидається: її задано під час встановлення вузла.
    std::memcpy(defaults.server_url, settings_.server_url,
                sizeof(defaults.server_url));
    settings_ = defaults;
    actions_.settings_changed();
    return "defaults restored (not saved; use save)\n";
  }
  if (command == "status") {
    return actions_.status();
  }
  if (command == "buffer") {
    return actions_.buffer_dump();
  }
  if (command == "net") {
    const std::string state = word_at(words, 1);
    if (state != "on" && state != "off") {
      return "usage: net on|off\n";
    }
    actions_.set_network_enabled(state == "on");
    return "network " + state + "\n";
  }
  if (command == "sim") {
    return handle_sim(word_at(words, 1), word_at(words, 2));
  }
  return "unknown command, type help\n";
}

std::string Console::handle_set(const std::string& key,
                                const std::string& value) {
  if (key.empty() || value.empty()) {
    return "usage: set <key> <value>\n";
  }
  const SettingResult result = set_setting(settings_, key, value);
  if (result != SettingResult::kOk) {
    return std::string("rejected: ") + setting_result_message(result) + "\n";
  }
  actions_.settings_changed();
  return key + " = " + value + " (not saved; use save)\n";
}

std::string Console::handle_sim(const std::string& what,
                                const std::string& argument) {
  if (what == "bounce") {
    const uint8_t channel =
        static_cast<uint8_t>(std::strtoul(argument.c_str(), nullptr, 10));
    if (channel != config::kChannelDoor && channel != config::kChannelWindow) {
      return "usage: sim bounce 1|2 (reed channels)\n";
    }
    return actions_.simulate_bounce(channel) ? "bounce simulated\n"
                                             : "bounce failed\n";
  }
  if (what == "badcmd") {
    return actions_.inject_forged_command();
  }
  return "usage: sim bounce <channel> | sim badcmd\n";
}
