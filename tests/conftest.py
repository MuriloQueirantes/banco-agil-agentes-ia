"""Fixtures compartilhadas.

As bases de teste são **escritas aqui**, não copiadas de `data/`. A diferença
importa: `data/clientes.csv` é uma base viva — a entrevista grava o novo score
nela, e `solicitacoes_aumento_limite.csv` cresce a cada pedido. Testes que
copiassem esses arquivos passariam num repositório recém-clonado e falhariam
depois de alguém abrir o Streamlit e conversar com a Ági.

Com os dados fixos abaixo, a suíte é determinística e independente do estado
da demonstração.
"""

from __future__ import annotations

import pytest

CLIENTES = """\
cpf,nome,data_nascimento,limite_atual,score
52601815906,Ana Beatriz Ramos,1988-03-14,3500.00,720
08301661305,Carlos Eduardo Lima,1975-11-02,1200.00,410
18609139034,Mariana Souza Prado,1993-07-25,9000.00,880
99603082430,Roberto Nunes Alves,1969-01-09,800.00,260
62819482112,Juliana Ferreira Dias,1990-12-30,5000.00,655
99351819019,Paulo Henrique Castro,1984-05-18,2000.00,505
93786579741,Fernanda Rocha Melo,2000-09-07,600.00,180
54323194897,Thiago Martins Barros,1997-02-21,15000.00,790
"""

SCORE_LIMITE = """\
score_min,score_max,limite_maximo
0,299,500.00
300,499,2000.00
500,699,7000.00
700,849,20000.00
850,1000,50000.00
"""

CABECALHO_SOLICITACOES = (
    "cpf_cliente,data_hora_solicitacao,limite_atual,"
    "novo_limite_solicitado,status_pedido\n"
)


@pytest.fixture()
def bases(tmp_path, monkeypatch):
    """Bases isoladas em disco, apontadas pelos repositórios via monkeypatch."""
    destino = tmp_path / "data"
    destino.mkdir()
    (destino / "clientes.csv").write_text(CLIENTES, encoding="utf-8")
    (destino / "score_limite.csv").write_text(SCORE_LIMITE, encoding="utf-8")
    solicitacoes = destino / "solicitacoes_aumento_limite.csv"
    solicitacoes.write_text(CABECALHO_SOLICITACOES, encoding="utf-8")

    from src.repositories import clientes, score_limite
    from src.repositories import solicitacoes as repo_sol

    monkeypatch.setattr(clientes, "CLIENTES_CSV", destino / "clientes.csv")
    monkeypatch.setattr(score_limite, "SCORE_LIMITE_CSV", destino / "score_limite.csv")
    monkeypatch.setattr(repo_sol, "SOLICITACOES_CSV", solicitacoes)

    return destino


@pytest.fixture()
def cliente_score_alto(bases):
    """Mariana: score 880 -> teto de R$ 50.000."""
    from src.repositories.clientes import buscar_por_cpf

    return buscar_por_cpf("18609139034")


@pytest.fixture()
def cliente_score_baixo(bases):
    """Roberto: score 260 -> teto de R$ 500."""
    from src.repositories.clientes import buscar_por_cpf

    return buscar_por_cpf("99603082430")
