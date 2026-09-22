"""Fórmula de score de crédito."""

from __future__ import annotations

import pytest

from src.config import SCORE_MAXIMO, SCORE_MINIMO, TETO_COMPONENTE_RENDA
from src.domain.models import RespostaEntrevista
from src.domain.scoring import calcular_score


def resposta(**kwargs) -> RespostaEntrevista:
    base = dict(
        renda_mensal=5000.0,
        tipo_emprego="formal",
        despesas_fixas=2000.0,
        num_dependentes=1,
        tem_dividas=False,
    )
    base.update(kwargs)
    return RespostaEntrevista(**base)


class TestFormula:
    def test_aplica_a_formula_do_enunciado(self):
        # renda: (5000 / 2001) * 30 = 74,96 | formal 300 | 1 dep. 80 | sem dívida 100
        detalhe = calcular_score(resposta())
        assert detalhe.componente_emprego == 300
        assert detalhe.componente_dependentes == 80
        assert detalhe.componente_dividas == 100
        assert detalhe.componente_renda == pytest.approx(74.96, abs=0.01)
        assert detalhe.score == 555

    @pytest.mark.parametrize(
        "tipo,peso", [("formal", 300), ("autonomo", 200), ("desempregado", 0)]
    )
    def test_pesos_de_emprego(self, tipo, peso):
        assert calcular_score(resposta(tipo_emprego=tipo)).componente_emprego == peso

    @pytest.mark.parametrize(
        "dependentes,peso", [(0, 100), (1, 80), (2, 60), (3, 30), (7, 30)]
    )
    def test_pesos_de_dependentes_com_faixa_3_mais(self, dependentes, peso):
        detalhe = calcular_score(resposta(num_dependentes=dependentes))
        assert detalhe.componente_dependentes == peso

    def test_dividas_penalizam_em_200_pontos_de_diferenca(self):
        com = calcular_score(resposta(tem_dividas=True))
        sem = calcular_score(resposta(tem_dividas=False))
        assert sem.score - com.score == 200


class TestLimitesDaEscala:
    def test_nunca_ultrapassa_1000(self):
        detalhe = calcular_score(
            resposta(renda_mensal=1_000_000, despesas_fixas=0, num_dependentes=0)
        )
        assert detalhe.score == SCORE_MAXIMO
        assert detalhe.soma_bruta > SCORE_MAXIMO

    def test_nunca_fica_negativo(self):
        detalhe = calcular_score(
            resposta(
                renda_mensal=0,
                despesas_fixas=9000,
                tipo_emprego="desempregado",
                num_dependentes=4,
                tem_dividas=True,
            )
        )
        assert detalhe.soma_bruta < 0
        assert detalhe.score == SCORE_MINIMO

    def test_teto_no_componente_de_renda_preserva_os_demais_fatores(self):
        """Sem o teto, renda altíssima saturaria o score sozinha.

        Com ele, quem tem renda enorme mas está desempregado e endividado
        ainda fica abaixo de quem tem emprego formal e nenhuma dívida.
        """
        rico_desempregado = calcular_score(
            resposta(
                renda_mensal=500_000,
                despesas_fixas=0,
                tipo_emprego="desempregado",
                num_dependentes=3,
                tem_dividas=True,
            )
        )
        assert rico_desempregado.componente_renda == TETO_COMPONENTE_RENDA
        assert rico_desempregado.score == 530

    def test_despesa_zero_nao_causa_divisao_por_zero(self):
        assert calcular_score(resposta(despesas_fixas=0)).score > 0


class TestExplicabilidade:
    def test_decomposicao_bate_com_a_soma_bruta(self):
        d = calcular_score(resposta())
        soma = (
            d.componente_renda
            + d.componente_emprego
            + d.componente_dependentes
            + d.componente_dividas
        )
        assert d.soma_bruta == pytest.approx(soma)

    def test_texto_de_auditoria_cita_todos_os_fatores(self):
        texto = calcular_score(resposta()).como_texto()
        for termo in ("renda", "emprego", "dependentes", "dívidas", "score final"):
            assert termo in texto
