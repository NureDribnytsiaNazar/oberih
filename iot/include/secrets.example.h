// Зразок secrets.h. Справжній файл генерує скрипт:
//   cd server; python -m scripts.provision_node --server-url https://...
// або скопіюйте цей файл у include/secrets.h і заповніть вручну.
// secrets.h не комітиться (.gitignore).
#pragma once

#define OBERIH_SERVER_URL "https://your-tunnel.example.com"
#define OBERIH_NODE_ID "00000000-0000-0000-0000-000000000000"
#define OBERIH_DEVICE_TOKEN "device-token-from-commissioning"
#define OBERIH_COMMAND_KEY \
  "0000000000000000000000000000000000000000000000000000000000000000"
// Кореневий сертифікат сервера чи тунелю (PEM). Без нього потрібен прапорець
// OBERIH_DEV_TLS (середовище esp32dev_devtls), що вимикає перевірку.
// #define OBERIH_ROOT_CA "-----BEGIN CERTIFICATE-----\n...\n"
