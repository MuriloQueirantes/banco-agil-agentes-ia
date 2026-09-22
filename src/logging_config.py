"""Logging estruturado da aplicação.

O desafio pede que erros sejam "registrados para análise técnica posterior
sem interromper abruptamente a interação". Toda falha capturada nas tools
é logada aqui com stack trace, enquanto o cliente recebe apenas uma
mensagem amigável.
"""

from __future__ import annotations

import logging
import sys

from src.config import LOG_DIR, LOG_FILE

_CONFIGURADO = False


def get_logger(nome: str) -> logging.Logger:
    global _CONFIGURADO
    if not _CONFIGURADO:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        formato = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        )

        arquivo = logging.FileHandler(LOG_FILE, encoding="utf-8")
        arquivo.setFormatter(formato)
        arquivo.setLevel(logging.DEBUG)

        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(formato)
        console.setLevel(logging.WARNING)

        raiz = logging.getLogger("banco_agil")
        raiz.setLevel(logging.DEBUG)
        raiz.handlers.clear()
        raiz.addHandler(arquivo)
        raiz.addHandler(console)
        raiz.propagate = False

        _CONFIGURADO = True

    return logging.getLogger(f"banco_agil.{nome}")
