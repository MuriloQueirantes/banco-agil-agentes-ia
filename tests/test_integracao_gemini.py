"""Testes de integração contra o Gemini real.

Estes testes gastam cota da API e são não determinísticos por natureza — por
isso ficam fora da execução padrão. Rode-os depois de configurar a chave, para
confirmar que o modelo escolhe as ferramentas certas:

    pytest -m integracao -v

Sem `GOOGLE_API_KEY` definida, a suíte inteira é pulada.
"""

from __future__ import annotations

import pytest

from src.config import GOOGLE_API_KEY

pytestmark = [
    pytest.mark.integracao,
    pytest.mark.skipif(
        not GOOGLE_API_KEY, reason="GOOGLE_API_KEY não configurada"
    ),
]

CPF_ANA = "526.018.159-06"
NASCIMENTO_ANA = "14/03/1988"
CPF_ROBERTO = "996.030.824-30"
NASCIMENTO_ROBERTO = "09/01/1969"


@pytest.fixture()
def sessao(bases):
    from src.atendimento import SessaoAtendimento

    return SessaoAtendimento()


def ferramentas(sessao) -> list[str]:
    return sessao.bastidores().ferramentas_do_turno


class TestConversaReal:
    def test_saudacao_pede_o_cpf_sem_usar_ferramenta(self, sessao):
        saudacao = sessao.iniciar()
        assert "cpf" in saudacao.lower()
        assert ferramentas(sessao) == []

    def test_autentica_e_atende_o_pedido_no_mesmo_turno(self, sessao):
        sessao.iniciar()
        resposta = sessao.enviar(
            f"oi, meu CPF é {CPF_ANA}, nasci em {NASCIMENTO_ANA}. "
            "Quanto tenho de limite?"
        )

        chamadas = ferramentas(sessao)
        assert "autenticar_cliente" in chamadas
        assert "transferir_para_credito" in chamadas
        assert "consultar_limite_credito" in chamadas

        assert sessao.bastidores().agente_atual == "credito"
        assert "3.500" in resposta or "3500" in resposta
        assert "Ana" in resposta

    def test_nao_revela_a_transferencia_ao_cliente(self, sessao):
        sessao.iniciar()
        sessao.enviar(f"{CPF_ANA}, {NASCIMENTO_ANA}")
        resposta = sessao.enviar("quanto está o dólar?")

        proibidos = [
            "transferir", "transferindo", "outro setor", "outro agente",
            "meu colega", "especialista em câmbio", "encaminhar você",
        ]
        minuscula = resposta.lower()
        assert not any(t in minuscula for t in proibidos), resposta
        assert "consultar_cotacao_moeda" in ferramentas(sessao)

    def test_recusa_atender_antes_da_autenticacao(self, sessao):
        sessao.iniciar()
        resposta = sessao.enviar("quero aumentar meu limite para 50 mil agora")

        assert sessao.bastidores().autenticado is False
        assert sessao.bastidores().agente_atual == "triagem"
        assert "solicitar_aumento_limite" not in ferramentas(sessao)
        assert any(t in resposta.lower() for t in ("cpf", "confirmar", "identidade"))

    def test_rejeicao_oferece_entrevista_e_aguarda_resposta(self, sessao, bases):
        sessao.iniciar()
        sessao.enviar(f"{CPF_ROBERTO}, {NASCIMENTO_ROBERTO}")
        resposta = sessao.enviar("quero aumentar meu limite para 5000 reais")

        assert sessao.bastidores().status_ultima_solicitacao == "rejeitado"
        # Oferece a entrevista, mas não transfere sem o cliente aceitar.
        assert "transferir_para_entrevista" not in ferramentas(sessao)
        assert any(
            t in resposta.lower()
            for t in ("perguntas", "entrevista", "reavaliar", "análise")
        )

    def test_recusa_assunto_fora_do_escopo_do_banco(self, sessao):
        sessao.iniciar()
        sessao.enviar(f"{CPF_ANA}, {NASCIMENTO_ANA}")
        resposta = sessao.enviar("me ensina a fazer um bolo de cenoura")

        assert "farinha" not in resposta.lower()
        assert sessao.encerrado is False

    def test_encerra_quando_o_cliente_se_despede(self, sessao):
        sessao.iniciar()
        sessao.enviar(f"{CPF_ANA}, {NASCIMENTO_ANA}")
        sessao.enviar("obrigado, era só isso mesmo. tchau!")

        assert "encerrar_atendimento" in ferramentas(sessao)
        assert sessao.encerrado is True

    def test_tres_falhas_encerram_o_atendimento(self, sessao):
        sessao.iniciar()
        sessao.enviar(f"{CPF_ANA}, 01/01/1990")
        assert sessao.bastidores().tentativas_autenticacao == 1

        sessao.enviar(f"{CPF_ANA}, 02/02/1991")
        assert sessao.bastidores().tentativas_autenticacao == 2

        sessao.enviar(f"{CPF_ANA}, 03/03/1992")
        assert sessao.bastidores().tentativas_autenticacao == 3
        assert sessao.encerrado is True


class TestEntrevistaReal:
    def test_conduz_as_cinco_perguntas_e_grava_o_novo_score(self, sessao, bases):
        from src.repositories.clientes import buscar_por_cpf

        sessao.iniciar()
        sessao.enviar(f"{CPF_ROBERTO}, {NASCIMENTO_ROBERTO}")
        sessao.enviar("quero aumentar meu limite para 5000 reais")
        sessao.enviar("sim, quero fazer as perguntas")

        assert sessao.bastidores().agente_atual == "entrevista"

        for resposta_do_cliente in (
            "ganho 8000 por mês",
            "tenho carteira assinada",
            "minhas despesas fixas são 2000",
            "não tenho dependentes",
            "não tenho dívidas",
        ):
            sessao.enviar(resposta_do_cliente)
            if sessao.bastidores().entrevista_concluida:
                break

        assert sessao.bastidores().entrevista_concluida is True
        assert buscar_por_cpf("99603082430").score == 620
