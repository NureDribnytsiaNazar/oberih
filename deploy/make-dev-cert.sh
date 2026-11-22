#!/bin/sh
# Самопідписаний TLS-сертифікат для локального розгортання (Nginx).
# Використання: ./deploy/make-dev-cert.sh [ім'я ...]   (за замовчуванням localhost bore.pub)
# Ключі в git не потрапляють (.gitignore).
set -eu

dir="$(cd "$(dirname "$0")" && pwd)/certs"
mkdir -p "$dir"
[ "$#" -eq 0 ] && set -- localhost bore.pub
san=""
for name in "$@"; do
  san="${san}DNS:${name},"
done
san="${san}IP:127.0.0.1"

openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -subj "/CN=$1" -addext "subjectAltName=$san" \
  -keyout "$dir/server.key" -out "$dir/server.crt"
chmod 644 "$dir/server.crt" "$dir/server.key"
echo "Сертифікат: $dir/server.crt ($san)"
