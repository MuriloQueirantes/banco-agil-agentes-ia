"""Cálculo do score de crédito (0 a 1000).

Implementa a fórmula ponderada do desafio. O cálculo é puro — sem I/O e sem
LLM — o que o torna trivialmente testável e auditável:

    score = (renda / (despesas + 1)) * PESO_RENDA
          + PESO_EMPREGO[tipo_emprego]
          + PESO_DEPENDENTES[num_dependentes]
          + PESO_DIVIDAS[tem_dividas]

Dois ajustes em relação ao enunciado, ambos documentados no README:

1. O componente de renda recebe um teto (TETO_COMPONENTE_RENDA). Sem ele,
   alguém com renda 50.000 e despesa 0 geraria 1.500.000 pontos e saturaria
   o score em 1000 sozinho, anulando os demais fatores.
2. O resultado final é fixado ("clampado") na faixa 0..1000, como exige o
   enunciado, já que a parcela de dívidas pode tornar a soma negativa.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.config import (
    PESO_DEPENDENTES,
    PESO_DIVIDAS,
    PESO_EMPREGO,
    PESO_RENDA,
    SCORE_MAXIMO,
    SCORE_MINIMO,
    TETO_COMPONENTE_RENDA,
)
from src.domain.models import RespostaEntrevista


@dataclass(frozen=True, slots=True)
class DetalheScore:
    """Score final + a contribuição de cada fator, para explicabilidade."""

    score: int
    componente_renda: float
    componente_emprego: int
    componente_dependentes: int
    componente_dividas: int
    soma_bruta: float

    def como_texto(self) -> str:
        return (
            f"renda/despesas: {self.componente_renda:.0f} pts | "
            f"emprego: {self.componente_emprego} pts | "
            f"dependentes: {self.componente_dependentes} pts | "
            f"dívidas: {self.componente_dividas} pts | "
            f"soma bruta: {self.soma_bruta:.0f} -> score final: {self.score}"
        )


def _chave_dependentes(num_dependentes: int) -> str:
    return str(num_dependentes) if num_dependentes <= 2 else "3+"


def calcular_score(resposta: RespostaEntrevista) -> DetalheScore:
    """Aplica a fórmula ponderada e devolve o score com sua decomposição."""
    componente_renda = min(
        (resposta.renda_mensal / (resposta.despesas_fixas + 1)) * PESO_RENDA,
        TETO_COMPONENTE_RENDA,
    )
    componente_emprego = PESO_EMPREGO[resposta.tipo_emprego]
    componente_dependentes = PESO_DEPENDENTES[
        _chave_dependentes(resposta.num_dependentes)
    ]
    componente_dividas = PESO_DIVIDAS["sim" if resposta.tem_dividas else "nao"]

    soma_bruta = (
        componente_renda
        + componente_emprego
        + componente_dependentes
        + componente_dividas
    )
    score = int(round(max(SCORE_MINIMO, min(SCORE_MAXIMO, soma_bruta))))

    return DetalheScore(
        score=score,
        componente_renda=componente_renda,
        componente_emprego=componente_emprego,
        componente_dependentes=componente_dependentes,
        componente_dividas=componente_dividas,
        soma_bruta=soma_bruta,
    )
