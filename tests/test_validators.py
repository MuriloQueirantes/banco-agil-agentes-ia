"""Validação e normalização das entradas do cliente."""

from __future__ import annotations

from datetime import date

import pytest

from src.domain.exceptions import EntradaInvalidaError
from src.domain.validators import (
    cpf_e_valido,
    mascarar_cpf,
    normalizar_booleano,
    normalizar_cpf,
    normalizar_data,
    normalizar_dependentes,
    normalizar_tipo_emprego,
    normalizar_valor_monetario,
)

CPF_VALIDO = "52601815906"


class TestCPF:
    def test_aceita_cpf_valido_com_e_sem_pontuacao(self):
        assert normalizar_cpf(CPF_VALIDO) == CPF_VALIDO
        assert normalizar_cpf("526.018.159-06") == CPF_VALIDO

    def test_preserva_zero_a_esquerda(self):
        # Regressão: pandas converteria para int e perderia o zero inicial.
        assert normalizar_cpf("083.016.613-05") == "08301661305"

    def test_rejeita_digito_verificador_incorreto(self):
        with pytest.raises(EntradaInvalidaError, match="não é válido"):
            normalizar_cpf("52601815907")

    def test_rejeita_todos_digitos_iguais(self):
        assert not cpf_e_valido("11111111111")

    @pytest.mark.parametrize("entrada", ["123", "", "abcdefghijk", "5260181590699"])
    def test_rejeita_tamanho_incorreto(self, entrada):
        with pytest.raises(EntradaInvalidaError):
            normalizar_cpf(entrada)

    def test_mascara_expoe_apenas_os_cinco_ultimos_digitos(self):
        mascarado = mascarar_cpf(CPF_VALIDO)
        assert mascarado == "***.***.159-06"
        assert CPF_VALIDO[:6] not in mascarado


class TestData:
    @pytest.mark.parametrize(
        "entrada", ["14/03/1988", "14-03-1988", "14.03.1988", "1988-03-14"]
    )
    def test_aceita_formatos_usuais(self, entrada):
        assert normalizar_data(entrada) == date(1988, 3, 14)

    def test_rejeita_data_futura(self):
        with pytest.raises(EntradaInvalidaError, match="futuro"):
            normalizar_data("01/01/2999")

    @pytest.mark.parametrize("entrada", ["ontem", "", "32/13/1988"])
    def test_rejeita_data_ilegivel(self, entrada):
        with pytest.raises(EntradaInvalidaError):
            normalizar_data(entrada)


class TestValorMonetario:
    @pytest.mark.parametrize(
        "entrada,esperado",
        [
            ("R$ 5.000,00", 5000.0),
            ("5000", 5000.0),
            ("5000.50", 5000.5),
            ("1.234,56", 1234.56),
            ("1,234.56", 1234.56),
            (7500, 7500.0),
            (7500.559, 7500.56),
        ],
    )
    def test_normaliza_formatos_brasileiros_e_internacionais(self, entrada, esperado):
        assert normalizar_valor_monetario(entrada) == esperado

    def test_rejeita_negativo(self):
        with pytest.raises(EntradaInvalidaError, match="negativo"):
            normalizar_valor_monetario(-100)

    def test_rejeita_texto_nao_numerico(self):
        with pytest.raises(EntradaInvalidaError):
            normalizar_valor_monetario("bastante dinheiro")


class TestCamposDaEntrevista:
    @pytest.mark.parametrize(
        "entrada,esperado",
        [
            ("formal", "formal"),
            ("CLT", "formal"),
            ("carteira assinada", "formal"),
            ("autônomo", "autonomo"),
            ("freelancer", "autonomo"),
            ("MEI", "autonomo"),
            ("desempregado", "desempregado"),
        ],
    )
    def test_reconhece_sinonimos_de_emprego(self, entrada, esperado):
        assert normalizar_tipo_emprego(entrada) == esperado

    def test_rejeita_emprego_desconhecido(self):
        with pytest.raises(EntradaInvalidaError, match="formal"):
            normalizar_tipo_emprego("astronauta")

    @pytest.mark.parametrize("entrada", ["sim", "SIM", "s", True, "tenho"])
    def test_booleano_verdadeiro(self, entrada):
        assert normalizar_booleano(entrada) is True

    @pytest.mark.parametrize("entrada", ["não", "nao", "N", False, "nenhuma"])
    def test_booleano_falso(self, entrada):
        assert normalizar_booleano(entrada) is False

    @pytest.mark.parametrize("entrada,esperado", [("2", 2), (3, 3), ("nenhum", 0), ("dois", 2)])
    def test_dependentes(self, entrada, esperado):
        assert normalizar_dependentes(entrada) == esperado

    def test_rejeita_dependentes_negativos(self):
        with pytest.raises(EntradaInvalidaError):
            normalizar_dependentes(-1)


class TestTextoDeMensagem:
    """Regressão: o Gemini devolve blocos tipados, não uma string simples."""

    def test_content_em_string(self):
        from langchain_core.messages import AIMessage

        from src.mensagens import texto_de

        assert texto_de(AIMessage(content="  Olá!  ")) == "Olá!"

    def test_content_em_blocos_concatena_apenas_o_texto(self):
        from langchain_core.messages import AIMessage

        from src.mensagens import texto_de

        mensagem = AIMessage(
            content=[
                {"type": "text", "text": "Olá, Ana!", "extras": {"signature": "Ev0C"}},
                {"type": "text", "text": " Seu limite é R$ 3.500,00."},
            ]
        )
        texto = texto_de(mensagem)
        assert texto == "Olá, Ana! Seu limite é R$ 3.500,00."
        assert "signature" not in texto
        assert "type" not in texto

    def test_ignora_blocos_que_nao_sao_texto(self):
        from langchain_core.messages import AIMessage

        from src.mensagens import texto_de

        mensagem = AIMessage(
            content=[
                {"type": "reasoning", "reasoning": "o cliente quer o limite"},
                {"type": "text", "text": "Seu limite é R$ 3.500,00."},
            ]
        )
        assert texto_de(mensagem) == "Seu limite é R$ 3.500,00."

    def test_content_vazio(self):
        from langchain_core.messages import AIMessage

        from src.mensagens import texto_de

        assert texto_de(AIMessage(content=[])) == ""
