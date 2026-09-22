"""Consulta de cotação de moedas via API pública.

Estratégia de resiliência em três camadas, pedida na seção de tratamento de
erros do desafio:

1. **AwesomeAPI** (`economia.awesomeapi.com.br`) — primária. Cotações do
   mercado brasileiro, sem necessidade de chave, com compra/venda e variação.
2. **ExchangeRate API** (`open.er-api.com`) — fallback. Se a primária cair ou
   der timeout, tentamos esta, que devolve apenas a paridade.
3. **ErroDeIntegracaoError** — se ambas falharem, o agente informa o cliente e
   oferece alternativas, em vez de quebrar a conversa.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import requests

from src.config import (
    COTACAO_API_FALLBACK,
    COTACAO_API_PRIMARIA,
    COTACAO_TIMEOUT_SEGUNDOS,
    MOEDAS_SUPORTADAS,
)
from src.domain.exceptions import EntradaInvalidaError, ErroDeIntegracaoError
from src.domain.validators import normalizar_texto
from src.logging_config import get_logger

logger = get_logger("services.cambio")

# Como o cliente costuma falar ("dólar", "euro") -> código ISO da moeda.
_APELIDOS: dict[str, str] = {
    "dolar": "USD", "dolares": "USD", "dollar": "USD", "usd": "USD",
    "dolar americano": "USD", "us$": "USD",
    "euro": "EUR", "euros": "EUR", "eur": "EUR",
    "libra": "GBP", "libras": "GBP", "libra esterlina": "GBP", "gbp": "GBP",
    "peso": "ARS", "peso argentino": "ARS", "ars": "ARS",
    "iene": "JPY", "yen": "JPY", "jpy": "JPY",
    "dolar canadense": "CAD", "cad": "CAD",
    "dolar australiano": "AUD", "aud": "AUD",
    "franco suico": "CHF", "franco": "CHF", "chf": "CHF",
    "bitcoin": "BTC", "btc": "BTC",
    "ethereum": "ETH", "eth": "ETH",
}


@dataclass(frozen=True, slots=True)
class Cotacao:
    moeda: str
    nome_moeda: str
    compra: float
    venda: float | None
    variacao_percentual: float | None
    atualizado_em: str
    fonte: str

    def como_texto(self) -> str:
        partes = [
            f"1 {self.moeda} ({self.nome_moeda}) = R$ {self.compra:.4f}".replace(".", ",")
        ]
        if self.venda is not None:
            partes.append(f"venda R$ {self.venda:.4f}".replace(".", ","))
        if self.variacao_percentual is not None:
            sinal = "+" if self.variacao_percentual >= 0 else ""
            partes.append(
                f"variação no dia {sinal}{self.variacao_percentual:.2f}%".replace(".", ",")
            )
        partes.append(f"atualizado em {self.atualizado_em}")
        partes.append(f"fonte: {self.fonte}")
        return " | ".join(partes)


def resolver_moeda(entrada: str) -> str:
    """Converte 'dólar', 'USD', 'dolares' etc. no código ISO."""
    chave = normalizar_texto(entrada)
    if not chave:
        return "USD"
    if chave.upper() in MOEDAS_SUPORTADAS:
        return chave.upper()
    if chave in _APELIDOS:
        return _APELIDOS[chave]
    for apelido, codigo in _APELIDOS.items():
        if apelido in chave:
            return codigo
    raise EntradaInvalidaError(
        f"Ainda não consulto a moeda '{entrada}'. "
        f"Posso consultar: {', '.join(sorted(MOEDAS_SUPORTADAS))}."
    )


def _formatar_data(bruto: str) -> str:
    for formato in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(bruto, formato).strftime("%d/%m/%Y às %H:%M")
        except ValueError:
            continue
    return bruto


def _consultar_primaria(moeda: str) -> Cotacao:
    url = COTACAO_API_PRIMARIA.format(par=f"{moeda}-BRL")
    resposta = requests.get(url, timeout=COTACAO_TIMEOUT_SEGUNDOS)
    resposta.raise_for_status()
    dados = resposta.json()

    chave = f"{moeda}BRL"
    if chave not in dados:
        raise ErroDeIntegracaoError(f"Resposta inesperada da API para {moeda}.")
    item = dados[chave]

    return Cotacao(
        moeda=moeda,
        nome_moeda=MOEDAS_SUPORTADAS.get(moeda, moeda),
        compra=float(item["bid"]),
        venda=float(item["ask"]) if item.get("ask") else None,
        variacao_percentual=float(item["pctChange"]) if item.get("pctChange") else None,
        atualizado_em=_formatar_data(item.get("create_date", "")),
        fonte="AwesomeAPI",
    )


def _consultar_fallback(moeda: str) -> Cotacao:
    url = COTACAO_API_FALLBACK.format(base=moeda)
    resposta = requests.get(url, timeout=COTACAO_TIMEOUT_SEGUNDOS)
    resposta.raise_for_status()
    dados = resposta.json()

    taxa = (dados.get("rates") or {}).get("BRL")
    if taxa is None:
        raise ErroDeIntegracaoError(
            f"A API de fallback não retornou a paridade {moeda}/BRL."
        )

    return Cotacao(
        moeda=moeda,
        nome_moeda=MOEDAS_SUPORTADAS.get(moeda, moeda),
        compra=float(taxa),
        venda=None,
        variacao_percentual=None,
        atualizado_em=dados.get("time_last_update_utc", "agora"),
        fonte="ExchangeRate API (fonte secundária)",
    )


def consultar_cotacao(moeda_bruta: str = "USD") -> Cotacao:
    """Cotação da moeda em reais, com fallback automático entre provedores."""
    moeda = resolver_moeda(moeda_bruta)

    try:
        return _consultar_primaria(moeda)
    except (requests.RequestException, ValueError, KeyError, ErroDeIntegracaoError) as exc:
        logger.warning("Fonte primária de câmbio indisponível (%s): %s", moeda, exc)

    try:
        return _consultar_fallback(moeda)
    except (requests.RequestException, ValueError, KeyError, ErroDeIntegracaoError) as exc:
        logger.error("Fonte de fallback também falhou (%s): %s", moeda, exc)
        raise ErroDeIntegracaoError(
            "Os provedores de cotação estão indisponíveis no momento."
        ) from exc
