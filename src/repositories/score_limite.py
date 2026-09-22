"""Acesso a `score_limite.csv` — política de limite por faixa de score."""

from __future__ import annotations

from src.config import SCORE_LIMITE_CSV
from src.domain.exceptions import ErroDeDadosError
from src.domain.models import FaixaScore
from src.repositories.csv_base import campo_float, campo_int, exigir_colunas, ler_csv

COLUNAS = ["score_min", "score_max", "limite_maximo"]


def listar_faixas() -> list[FaixaScore]:
    linhas = ler_csv(SCORE_LIMITE_CSV)
    exigir_colunas(linhas, set(COLUNAS), SCORE_LIMITE_CSV.name)
    faixas = [
        FaixaScore(
            score_min=campo_int(linha, "score_min", SCORE_LIMITE_CSV.name),
            score_max=campo_int(linha, "score_max", SCORE_LIMITE_CSV.name),
            limite_maximo=campo_float(linha, "limite_maximo", SCORE_LIMITE_CSV.name),
        )
        for linha in linhas
    ]
    if not faixas:
        raise ErroDeDadosError(
            f"A tabela '{SCORE_LIMITE_CSV.name}' não possui nenhuma faixa."
        )
    return sorted(faixas, key=lambda f: f.score_min)


def limite_maximo_para_score(score: int) -> float:
    """Teto de limite que o score atual autoriza.

    Se o score cair fora de todas as faixas (base incompleta), aplicamos a
    faixa mais próxima em vez de falhar — negar crédito por erro de cadastro
    seria pior do que usar a política mais conservadora disponível.
    """
    faixas = listar_faixas()
    for faixa in faixas:
        if faixa.contem(score):
            return faixa.limite_maximo
    if score < faixas[0].score_min:
        return faixas[0].limite_maximo
    return faixas[-1].limite_maximo


def score_minimo_para_limite(limite: float) -> int | None:
    """Menor score que autoriza o limite desejado (None se nenhum autoriza)."""
    for faixa in listar_faixas():
        if faixa.limite_maximo >= limite:
            return faixa.score_min
    return None
