"""Camada de persistência: autenticação, política de limite e auditoria."""

from __future__ import annotations

from datetime import date

import pytest

from src.domain.exceptions import (
    ClienteNaoEncontradoError,
    EntradaInvalidaError,
    ErroDeDadosError,
)
from src.repositories import clientes as repo_clientes
from src.repositories import score_limite as repo_score
from src.repositories import solicitacoes as repo_sol
from src.repositories.csv_base import ler_csv


class TestAutenticacao:
    def test_autentica_com_cpf_e_data_corretos(self, bases):
        cliente = repo_clientes.autenticar("526.018.159-06", date(1988, 3, 14))
        assert cliente.nome == "Ana Beatriz Ramos"
        assert cliente.primeiro_nome == "Ana"

    def test_recusa_data_de_nascimento_errada(self, bases):
        with pytest.raises(ClienteNaoEncontradoError):
            repo_clientes.autenticar("526.018.159-06", date(1988, 3, 15))

    def test_recusa_cpf_inexistente(self, bases):
        with pytest.raises(ClienteNaoEncontradoError):
            repo_clientes.autenticar("111.444.777-35", date(1988, 3, 14))

    def test_mensagem_nao_revela_se_o_cpf_existe(self, bases):
        """Impede enumeração de contas pela diferença nas mensagens."""
        with pytest.raises(ClienteNaoEncontradoError) as cpf_inexistente:
            repo_clientes.autenticar("111.444.777-35", date(1988, 3, 14))
        with pytest.raises(ClienteNaoEncontradoError) as data_errada:
            repo_clientes.autenticar("526.018.159-06", date(1990, 1, 1))
        assert str(cpf_inexistente.value) == str(data_errada.value)

    def test_recusa_cpf_com_digito_verificador_invalido(self, bases):
        with pytest.raises(EntradaInvalidaError):
            repo_clientes.autenticar("111.111.111-11", date(1988, 3, 14))

    def test_encontra_cliente_cujo_cpf_comeca_com_zero(self, bases):
        cliente = repo_clientes.buscar_por_cpf("08301661305")
        assert cliente is not None
        assert cliente.nome == "Carlos Eduardo Lima"

    def test_base_ausente_vira_erro_de_dados_tratavel(self, bases, monkeypatch):
        monkeypatch.setattr(
            repo_clientes, "CLIENTES_CSV", bases / "nao_existe.csv"
        )
        with pytest.raises(ErroDeDadosError, match="não foi encontrada"):
            repo_clientes.listar_clientes()


class TestAtualizacaoDeScore:
    def test_persiste_o_novo_score(self, bases, cliente_score_baixo):
        atualizado = repo_clientes.atualizar_score(cliente_score_baixo.cpf, 777)
        assert atualizado.score == 777
        assert repo_clientes.buscar_por_cpf(cliente_score_baixo.cpf).score == 777

    def test_nao_altera_as_demais_colunas_nem_os_outros_clientes(
        self, bases, cliente_score_baixo
    ):
        antes = {c.cpf: c for c in repo_clientes.listar_clientes()}
        repo_clientes.atualizar_score(cliente_score_baixo.cpf, 999)
        depois = {c.cpf: c for c in repo_clientes.listar_clientes()}

        assert len(antes) == len(depois)
        for cpf, cliente in antes.items():
            if cpf == cliente_score_baixo.cpf:
                assert depois[cpf].limite_atual == cliente.limite_atual
                assert depois[cpf].nome == cliente.nome
            else:
                assert depois[cpf] == cliente

    def test_cpf_inexistente_levanta_erro(self, bases):
        with pytest.raises(ClienteNaoEncontradoError):
            repo_clientes.atualizar_score("11144477735", 500)


class TestPoliticaDeLimite:
    @pytest.mark.parametrize(
        "score,teto",
        [(0, 500), (299, 500), (300, 2000), (655, 7000), (720, 20000), (1000, 50000)],
    )
    def test_teto_por_faixa_de_score(self, bases, score, teto):
        assert repo_score.limite_maximo_para_score(score) == teto

    def test_score_minimo_necessario_para_um_limite(self, bases):
        assert repo_score.score_minimo_para_limite(1500) == 300
        assert repo_score.score_minimo_para_limite(20000) == 700

    def test_limite_acima_de_toda_a_politica_nao_tem_score_suficiente(self, bases):
        assert repo_score.score_minimo_para_limite(999_999) is None


class TestSolicitacoes:
    def test_registra_pedido_com_as_colunas_exigidas(self, bases, cliente_score_alto):
        repo_sol.registrar_pedido(cliente_score_alto.cpf, 9000.0, 15000.0)

        linhas = ler_csv(bases / "solicitacoes_aumento_limite.csv")
        assert len(linhas) == 1
        assert set(linhas[0]) == {
            "cpf_cliente",
            "data_hora_solicitacao",
            "limite_atual",
            "novo_limite_solicitado",
            "status_pedido",
        }
        assert linhas[0]["status_pedido"] == "pendente"
        assert linhas[0]["novo_limite_solicitado"] == "15000.00"

    def test_timestamp_em_iso_8601(self, bases, cliente_score_alto):
        from datetime import datetime

        pedido = repo_sol.registrar_pedido(cliente_score_alto.cpf, 100.0, 200.0)
        # Não levanta: o formato é ISO 8601 válido.
        datetime.fromisoformat(pedido.data_hora_solicitacao)

    def test_atualiza_status_da_linha_correta(self, bases, cliente_score_alto):
        primeiro = repo_sol.registrar_pedido(cliente_score_alto.cpf, 100.0, 200.0)
        segundo = repo_sol.registrar_pedido(cliente_score_alto.cpf, 100.0, 300.0)
        repo_sol.atualizar_status(segundo, "aprovado")

        linhas = ler_csv(bases / "solicitacoes_aumento_limite.csv")
        por_valor = {l["novo_limite_solicitado"]: l["status_pedido"] for l in linhas}
        assert por_valor["300.00"] == "aprovado"
        assert por_valor["200.00"] == "pendente"
        assert primeiro.status_pedido == "pendente"

    def test_status_desconhecido_e_rejeitado(self, bases, cliente_score_alto):
        pedido = repo_sol.registrar_pedido(cliente_score_alto.cpf, 100.0, 200.0)
        with pytest.raises(ErroDeDadosError, match="Status"):
            repo_sol.atualizar_status(pedido, "em_analise_manual")

    def test_historico_filtra_por_cpf(self, bases, cliente_score_alto, cliente_score_baixo):
        repo_sol.registrar_pedido(cliente_score_alto.cpf, 100.0, 200.0)
        repo_sol.registrar_pedido(cliente_score_baixo.cpf, 100.0, 300.0)

        historico = repo_sol.listar_por_cpf(cliente_score_alto.cpf)
        assert len(historico) == 1
        assert historico[0].novo_limite_solicitado == 200.0


class TestEscritaAtomica:
    def test_falha_no_meio_da_escrita_nao_corrompe_o_arquivo(
        self, bases, monkeypatch, cliente_score_baixo
    ):
        from src.repositories import csv_base

        original = csv_base.os.replace

        def replace_que_falha(*args, **kwargs):
            raise OSError("disco cheio")

        monkeypatch.setattr(csv_base.os, "replace", replace_que_falha)
        with pytest.raises(ErroDeDadosError):
            repo_clientes.atualizar_score(cliente_score_baixo.cpf, 1)

        monkeypatch.setattr(csv_base.os, "replace", original)
        # O arquivo original continua íntegro e legível.
        assert len(repo_clientes.listar_clientes()) == 8
        assert repo_clientes.buscar_por_cpf(cliente_score_baixo.cpf).score == 260
