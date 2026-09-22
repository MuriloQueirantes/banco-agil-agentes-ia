"""Fábrica do modelo de linguagem (Google Gemini).

Isolar a criação do LLM num único ponto mantém os agentes agnósticos ao
provedor: trocar de modelo (ou de provedor) é mexer só neste arquivo.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI

from src.config import GOOGLE_API_KEY, LLM_MODEL, LLM_TEMPERATURE
from src.domain.exceptions import BancoAgilError


class ConfiguracaoAusenteError(BancoAgilError):
    """A chave de API do provedor de LLM não foi configurada."""


@lru_cache(maxsize=4)
def criar_llm(modelo: str | None = None, temperatura: float | None = None):
    """Devolve o cliente de chat, memoizado por (modelo, temperatura)."""
    if not GOOGLE_API_KEY:
        raise ConfiguracaoAusenteError(
            "A variável de ambiente GOOGLE_API_KEY não está definida. "
            "Crie um arquivo .env a partir de .env.example e insira sua chave "
            "do Google AI Studio (https://aistudio.google.com/apikey)."
        )

    return ChatGoogleGenerativeAI(
        model=modelo or LLM_MODEL,
        temperature=LLM_TEMPERATURE if temperatura is None else temperatura,
        google_api_key=GOOGLE_API_KEY,
        max_retries=2,
        timeout=45,
    )
