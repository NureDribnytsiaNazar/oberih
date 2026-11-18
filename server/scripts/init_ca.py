"""Ініціалізація власного центру сертифікації для IoT-вузлів.

Створює самопідписаний кореневий сертифікат і ключ у каталозі CA_DIR
(за замовчуванням server/ca, у .gitignore). Наявний центр не
перезаписується. Запуск із каталогу server:
    python -m scripts.init_ca
"""

from app.config import settings
from app.services.certificates import create_ca


def main() -> None:
    """Точка входу командного рядка."""
    try:
        cert_path = create_ca(settings.ca_dir)
    except FileExistsError:
        print(f"Центр сертифікації вже існує: {settings.ca_dir.resolve()}")
        return
    print(f"Кореневий сертифікат створено: {cert_path.resolve()}")
    print("Ключ центру сертифікації не додавайте до репозиторію.")


if __name__ == "__main__":
    main()
