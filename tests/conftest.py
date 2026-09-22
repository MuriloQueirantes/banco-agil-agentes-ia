"""Fixtures compartilhadas.

Todos os testes que tocam CSV trabalham sobre uma cópia temporária das bases,
para que a suíte jamais escreva em `data/` do repositório.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
DADOS_REAIS = RAIZ / "data"


@pytest.fixture()
def bases(tmp_path, monkeypatch):
    """Cópia isolada de clientes.csv, score_limite.csv e solicitacoes."""
    destino = tmp_path / "data"
    destino.mkdir()
    for nome in ("clientes.csv", "score_limite.csv"):
        shutil.copy(DADOS_REAIS / nome, destino / nome)
    solicitacoes = destino / "solicitacoes_aumento_limite.csv"
    solicitacoes.write_text(
        "cpf_cliente,data_hora_solicitacao,limite_atual,"
        "novo_limite_solicitado,status_pedido\n",
        encoding="utf-8",
    )

    from src.repositories import clientes, score_limite, solicitacoes as repo_sol

    monkeypatch.setattr(clientes, "CLIENTES_CSV", destino / "clientes.csv")
    monkeypatch.setattr(score_limite, "SCORE_LIMITE_CSV", destino / "score_limite.csv")
    monkeypatch.setattr(repo_sol, "SOLICITACOES_CSV", solicitacoes)

    return destino


@pytest.fixture()
def cliente_score_alto(bases):
    """Mariana: score 880 -> teto de R$ 50.000."""
    from src.repositories.clientes import listar_clientes

    return next(c for c in listar_clientes() if c.score == 880)


@pytest.fixture()
def cliente_score_baixo(bases):
    """Roberto: score 260 -> teto de R$ 500."""
    from src.repositories.clientes import listar_clientes

    return next(c for c in listar_clientes() if c.score == 260)
