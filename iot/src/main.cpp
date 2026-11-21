// Точка входу прошивки: лише склеювання модулів через NodeApp.
#include <Arduino.h>

#include "node_app.h"

namespace {
NodeApp app;  // єдиний глобальний об'єкт програми вузла
}

void setup() { app.begin(); }

void loop() { app.loop(); }
