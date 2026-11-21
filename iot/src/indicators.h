// ІК-6: індикація режиму та стану зв'язку світлодіодом RGB і зумером.
// Чиста функція: за станом вузла й часом повертає, що вмикати. Виведення
// на піни виконує node_app.cpp.
//
// Режими: знято — зелений; «Вдома» — жовтий; повна охорона — червоний;
// затримки — мигання червоного 2 Гц; тривога — швидке мигання й тон.
// Немає зв'язку — синій спалах щосекунди й короткий сигнал кожні 10 с;
// відновлення зв'язку — синій постійно 3 с і короткий сигнал.
#pragma once

#include <cstdint>

#include "domain.h"

struct IndicatorInput {
  Mode mode;
  bool offline;
  bool restored;               // зв'язок щойно відновлено
  uint32_t restored_at_ms;     // момент відновлення
  uint32_t now_ms;
};

struct IndicatorOutput {
  bool red;
  bool green;
  bool blue;
  uint16_t tone_hz;  // 0 — зумер вимкнено
};

IndicatorOutput indicator_state(const IndicatorInput& input);
