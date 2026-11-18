"""Клас відповіді API з явним кодуванням UTF-8."""

from fastapi.responses import JSONResponse


class UTF8JSONResponse(JSONResponse):
    """JSON із заголовком charset=utf-8.

    Деякі клієнти (зокрема Windows PowerShell 5.1) без явного charset
    декодують тіло як ISO-8859-1 і псують кирилицю.
    """

    media_type = "application/json; charset=utf-8"
