"""Telegram. O token nunca é impresso em log nem em mensagem de erro."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


def enviar_telegram(texto: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[telegram desativado: faltam TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID]")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    ok = True
    for i in range(0, len(texto), 3800):  # limite do Telegram é 4096
        corpo = json.dumps({"chat_id": chat, "text": texto[i:i + 3800]}).encode()
        req = urllib.request.Request(url, corpo, {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                ok = ok and r.status == 200
        except urllib.error.HTTPError as e:
            print(f"[telegram falhou: HTTP {e.code}]")
            ok = False
        except Exception as e:
            print(f"[telegram falhou: {type(e).__name__}]")  # sem a URL: ela contém o token
            ok = False
    return ok


# Os testes trocam esta função por uma falsa.
ENVIAR = enviar_telegram
