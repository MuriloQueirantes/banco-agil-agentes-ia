"""Testes de fluxo ponta a ponta do grafo, com LLM roteirizado.

Substituímos o Gemini por um modelo falso que devolve uma sequência fixa de
respostas. Isso permite verificar **o que é responsabilidade do sistema** —
roteamento, handoff, contagem de tentativas, escrita em CSV, encerramento —
de forma determinística, sem rede, sem custo e sem a variabilidade do LLM.

O que é responsabilidade do *modelo* (escolher a ferramenta certa, redigir a
fala) é validado à parte, pelo roteiro de testes manuais do README.
"""

from __future__ import annotations

import itertools

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.repositories.csv_base import ler_csv
from src.state import estado_inicial

CPF_ANA = "52601815906"           # score 720, limite R$ 3.500, teto R$ 20.000
NASCIMENTO_ANA = "14/03/1988"
CPF_ROBERTO = "99603082430"       # score 260, limite R$ 800, teto R$ 500
NASCIMENTO_ROBERTO = "09/01/1969"

_contador = itertools.count(1)


def chamar(nome: str, **args) -> AIMessage:
    """AIMessage pedindo a execução de uma ferramenta."""
    return AIMessage(
        content="",
        tool_calls=[
            {"name": nome, "args": args, "id": f"call_{next(_contador)}", "type": "tool_call"}
        ],
    )


def falar(texto: str) -> AIMessage:
    """AIMessage sem tool call — encerra o turno e devolve a vez ao cliente."""
    return AIMessage(content=texto)


class LLMRoteirizado:
    """Modelo falso que devolve as respostas de um roteiro, em ordem."""

    def __init__(self, roteiro):
        self.roteiro = list(roteiro)
        self.ferramentas_vistas: list[list[str]] = []

    def bind_tools(self, ferramentas):
        self.ferramentas_vistas.append([f.name for f in ferramentas])
        return self

    def invoke(self, mensagens):
        if not self.roteiro:
            raise AssertionError(
                "O grafo pediu mais uma resposta do que o roteiro previa — "
                "provável loop no roteamento."
            )
        return self.roteiro.pop(0)


@pytest.fixture()
def executar(bases, monkeypatch):
    """Roda o grafo com um roteiro e devolve (estado_final, llm)."""

    def _executar(roteiro, entrada_do_cliente="Olá", estado=None):
        from src import graph as modulo_grafo

        llm = LLMRoteirizado(roteiro)
        monkeypatch.setattr(modulo_grafo, "criar_llm", lambda *a, **k: llm)

        compilado = modulo_grafo.construir_grafo()
        inicial = estado or estado_inicial()
        inicial = {**inicial, "messages": [*inicial.get("messages", []),
                                           HumanMessage(content=entrada_do_cliente)]}
        final = compilado.invoke(
            inicial, config={"configurable": {"thread_id": "teste"}}
        )
        return final, llm

    return _executar


def texto_final(estado) -> str:
    return estado["messages"][-1].content


class TestEscopoDasFerramentas:
    def test_cada_agente_so_enxerga_as_proprias_ferramentas(self, executar):
        """O agente de câmbio não tem como gravar um pedido de aumento."""
        from src.agents.definicoes import AGENTES

        nomes = {
            agente: {f.name for f in definicao.ferramentas}
            for agente, definicao in AGENTES.items()
        }

        assert "autenticar_cliente" in nomes["triagem"]
        assert "autenticar_cliente" not in nomes["credito"]
        assert "solicitar_aumento_limite" in nomes["credito"]
        assert "solicitar_aumento_limite" not in nomes["cambio"]
        assert "consultar_cotacao_moeda" not in nomes["credito"]
        assert "calcular_e_salvar_novo_score" in nomes["entrevista"]
        assert "calcular_e_salvar_novo_score" not in nomes["triagem"]
        # Todo agente pode encerrar a conversa a pedido do cliente.
        assert all("encerrar_atendimento" in fs for fs in nomes.values())


class TestAutenticacao:
    def test_autentica_e_transfere_para_credito_em_um_unico_turno(self, executar):
        """O cliente recebe UMA resposta; a transferência é invisível."""
        estado, _ = executar(
            [
                chamar("autenticar_cliente", cpf=CPF_ANA, data_nascimento=NASCIMENTO_ANA),
                chamar("transferir_para_credito"),
                falar("Oi, Ana! Seu limite atual é de R$ 3.500,00."),
            ],
            entrada_do_cliente=f"oi, meu cpf é {CPF_ANA} e nasci em {NASCIMENTO_ANA}, "
                               "quero ver meu limite",
        )

        assert estado["autenticado"] is True
        assert estado["nome_cliente"] == "Ana Beatriz Ramos"
        assert estado["cpf"] == CPF_ANA
        assert estado["agente_atual"] == "credito"
        assert estado["tentativas_autenticacao"] == 0

        faladas = [
            m for m in estado["messages"]
            if isinstance(m, AIMessage) and m.content and not m.tool_calls
        ]
        assert len(faladas) == 1, "o cliente deve receber uma única resposta no turno"

    def test_erro_de_formato_nao_consome_tentativa(self, executar):
        estado, _ = executar(
            [
                chamar("autenticar_cliente", cpf="123", data_nascimento="ontem"),
                falar("Preciso do CPF completo, com 11 dígitos."),
            ],
            entrada_do_cliente="meu cpf é 123",
        )
        assert estado["tentativas_autenticacao"] == 0
        assert estado["autenticado"] is False

    def test_dados_incorretos_consomem_uma_tentativa(self, executar):
        estado, _ = executar(
            [
                chamar("autenticar_cliente", cpf=CPF_ANA, data_nascimento="01/01/1990"),
                falar("Os dados não conferem. Pode conferir e repetir?"),
            ],
        )
        assert estado["tentativas_autenticacao"] == 1
        assert estado["autenticado"] is False
        assert estado["encerrado"] is False

    def test_terceira_falha_consecutiva_encerra_o_atendimento(self, executar):
        estado = estado_inicial()
        estado["tentativas_autenticacao"] = 2  # duas já falharam

        final, _ = executar(
            [
                chamar("autenticar_cliente", cpf=CPF_ANA, data_nascimento="02/02/1991"),
                chamar(
                    "encerrar_atendimento",
                    mensagem_de_despedida="Não consegui confirmar seus dados. "
                                          "Procure um canal oficial do Banco Ágil. Até logo!",
                    motivo="limite de tentativas de autenticação",
                ),
                falar("Não consegui confirmar seus dados. "
                      "Procure um canal oficial do Banco Ágil. Até logo!"),
            ],
            estado=estado,
        )

        assert final["tentativas_autenticacao"] == 3
        assert final["encerrado"] is True
        assert final["autenticado"] is False
        assert "Até logo" in texto_final(final)

    def test_transferencia_e_bloqueada_sem_autenticacao(self, executar):
        """Mesmo que o modelo tente pular a etapa, o estado não deixa."""
        estado, _ = executar(
            [
                chamar("transferir_para_credito"),
                falar("Antes disso, preciso confirmar sua identidade. Qual é o seu CPF?"),
            ],
            entrada_do_cliente="quero aumentar meu limite agora",
        )
        assert estado["agente_atual"] == "triagem"
        assert estado["autenticado"] is False


class TestFluxoDeCredito:
    def _autenticado(self, cpf: str, nome: str, agente: str = "credito") -> dict:
        estado = estado_inicial()
        estado.update(
            autenticado=True, cpf=cpf, nome_cliente=nome, agente_atual=agente
        )
        return estado

    def test_pedido_dentro_do_teto_do_score_e_aprovado(self, executar, bases):
        estado, _ = executar(
            [
                chamar("solicitar_aumento_limite", novo_limite=10000),
                falar("Boa notícia, Ana: seu aumento para R$ 10.000,00 foi aprovado!"),
            ],
            entrada_do_cliente="quero aumentar para 10 mil",
            estado=self._autenticado(CPF_ANA, "Ana Beatriz Ramos"),
        )

        assert estado["status_ultima_solicitacao"] == "aprovado"

        linhas = ler_csv(bases / "solicitacoes_aumento_limite.csv")
        assert len(linhas) == 1
        assert linhas[0]["cpf_cliente"] == CPF_ANA
        assert linhas[0]["limite_atual"] == "3500.00"
        assert linhas[0]["novo_limite_solicitado"] == "10000.00"
        assert linhas[0]["status_pedido"] == "aprovado"

    def test_pedido_acima_do_teto_e_rejeitado_e_fica_registrado(self, executar, bases):
        estado, _ = executar(
            [
                chamar("solicitar_aumento_limite", novo_limite=5000),
                falar("Infelizmente não consegui aprovar agora. Posso fazer algumas "
                      "perguntas rápidas para reavaliar sua análise?"),
            ],
            estado=self._autenticado(CPF_ROBERTO, "Roberto Nunes Alves"),
        )

        assert estado["status_ultima_solicitacao"] == "rejeitado"
        linhas = ler_csv(bases / "solicitacoes_aumento_limite.csv")
        assert linhas[0]["status_pedido"] == "rejeitado"

    def test_valor_menor_que_o_limite_atual_nao_gera_registro(self, executar, bases):
        estado, _ = executar(
            [
                chamar("solicitar_aumento_limite", novo_limite=1000),
                falar("Seu limite atual já é de R$ 3.500,00. Qual valor você gostaria?"),
            ],
            estado=self._autenticado(CPF_ANA, "Ana Beatriz Ramos"),
        )
        assert ler_csv(bases / "solicitacoes_aumento_limite.csv") == []
        assert estado["status_ultima_solicitacao"] is None


class TestEntrevistaERecalculo:
    def test_entrevista_atualiza_score_e_devolve_ao_credito(self, executar, bases):
        """Fluxo completo: rejeição → entrevista → novo score → aprovação."""
        from src.repositories import clientes as repo_clientes

        estado = estado_inicial()
        estado.update(
            autenticado=True,
            cpf=CPF_ROBERTO,
            nome_cliente="Roberto Nunes Alves",
            agente_atual="credito",
        )

        # Passo 1 — pedido rejeitado, agente oferece a entrevista.
        estado, _ = executar(
            [
                chamar("solicitar_aumento_limite", novo_limite=5000),
                falar("Não consegui aprovar agora. Posso fazer algumas perguntas "
                      "rápidas para reavaliar?"),
            ],
            entrada_do_cliente="quero 5 mil de limite",
            estado=estado,
        )
        assert estado["status_ultima_solicitacao"] == "rejeitado"
        assert repo_clientes.buscar_por_cpf(CPF_ROBERTO).score == 260

        # Passo 2 — cliente aceita; entrevista roda e devolve ao crédito.
        estado, _ = executar(
            [
                chamar("transferir_para_entrevista"),
                falar("Qual é a sua renda mensal aproximada?"),
            ],
            entrada_do_cliente="sim, pode perguntar",
            estado=estado,
        )
        assert estado["agente_atual"] == "entrevista"

        estado, _ = executar(
            [
                chamar(
                    "calcular_e_salvar_novo_score",
                    renda_mensal=8000,
                    tipo_emprego="formal",
                    despesas_fixas=2000,
                    num_dependentes=0,
                    tem_dividas="nao",
                ),
                chamar("transferir_para_credito"),
                falar("Sua análise foi atualizada. Quer que eu reavalie o aumento?"),
            ],
            entrada_do_cliente="8 mil, formal, 2 mil de despesa, sem dependentes, sem dívidas",
            estado=estado,
        )

        # renda: (8000/2001)*30 = 119,94 | formal 300 | 0 dep. 100 | sem dívida 100
        cliente = repo_clientes.buscar_por_cpf(CPF_ROBERTO)
        assert cliente.score == 620
        assert estado["entrevista_concluida"] is True
        assert estado["agente_atual"] == "credito"

        # Passo 3 — com score 620 (teto R$ 7.000), o mesmo pedido agora passa.
        estado, _ = executar(
            [
                chamar("solicitar_aumento_limite", novo_limite=5000),
                falar("Agora sim! Seu aumento para R$ 5.000,00 foi aprovado."),
            ],
            entrada_do_cliente="sim, reavalia por favor",
            estado=estado,
        )
        assert estado["status_ultima_solicitacao"] == "aprovado"

        linhas = ler_csv(bases / "solicitacoes_aumento_limite.csv")
        assert [l["status_pedido"] for l in linhas] == ["rejeitado", "aprovado"]

    def test_resposta_invalida_na_entrevista_nao_grava_score(self, executar, bases):
        from src.repositories import clientes as repo_clientes

        estado = estado_inicial()
        estado.update(
            autenticado=True,
            cpf=CPF_ROBERTO,
            nome_cliente="Roberto Nunes Alves",
            agente_atual="entrevista",
        )
        _, _ = executar(
            [
                chamar(
                    "calcular_e_salvar_novo_score",
                    renda_mensal=5000,
                    tipo_emprego="astronauta",
                    despesas_fixas=1000,
                    num_dependentes=0,
                    tem_dividas="nao",
                ),
                falar("Você trabalha com carteira assinada, como autônomo, ou "
                      "está sem trabalho no momento?"),
            ],
            estado=estado,
        )
        assert repo_clientes.buscar_por_cpf(CPF_ROBERTO).score == 260


class TestCambio:
    def test_consulta_cotacao_e_encerra(self, executar, monkeypatch):
        from src.services import cambio as servico
        from src.tools import cambio_tools

        cotacao = servico.Cotacao(
            moeda="USD",
            nome_moeda="Dólar americano",
            compra=5.1234,
            venda=5.1240,
            variacao_percentual=-0.21,
            atualizado_em="22/09/2026 às 18:30",
            fonte="AwesomeAPI",
        )
        monkeypatch.setattr(
            cambio_tools.servico_cambio, "consultar_cotacao", lambda m: cotacao
        )

        estado = estado_inicial()
        estado.update(
            autenticado=True, cpf=CPF_ANA, nome_cliente="Ana", agente_atual="cambio"
        )

        final, _ = executar(
            [
                chamar("consultar_cotacao_moeda", moeda="dólar"),
                falar("O dólar está a R$ 5,1234 (atualizado às 18:30). Posso ajudar em algo mais?"),
            ],
            entrada_do_cliente="quanto está o dólar?",
            estado=estado,
        )
        assert "5,1234" in texto_final(final)

    def test_api_fora_do_ar_nao_derruba_a_conversa(self, executar, monkeypatch):
        from src.domain.exceptions import ErroDeIntegracaoError
        from src.tools import cambio_tools

        def indisponivel(_):
            raise ErroDeIntegracaoError("provedores fora do ar")

        monkeypatch.setattr(
            cambio_tools.servico_cambio, "consultar_cotacao", indisponivel
        )

        estado = estado_inicial()
        estado.update(
            autenticado=True, cpf=CPF_ANA, nome_cliente="Ana", agente_atual="cambio"
        )
        final, _ = executar(
            [
                chamar("consultar_cotacao_moeda", moeda="dólar"),
                falar("Não consegui consultar a cotação agora. Pode tentar em alguns "
                      "minutos? Enquanto isso, posso ajudar com outro assunto."),
            ],
            estado=estado,
        )
        assert final["encerrado"] is False
        assert "não consegui" in texto_final(final).lower()


class TestResilienciaDoGrafo:
    def test_falha_do_llm_devolve_mensagem_de_contingencia(self, bases, monkeypatch):
        """Se o provedor cair, o atendimento responde em vez de estourar."""
        from src import graph as modulo_grafo

        class LLMQuebrado:
            def bind_tools(self, _):
                return self

            def invoke(self, _):
                raise RuntimeError("503 Service Unavailable")

        monkeypatch.setattr(modulo_grafo, "criar_llm", lambda *a, **k: LLMQuebrado())
        compilado = modulo_grafo.construir_grafo()

        final = compilado.invoke(
            {**estado_inicial(), "messages": [HumanMessage(content="oi")]},
            config={"configurable": {"thread_id": "t"}},
        )
        assert modulo_grafo.MENSAGEM_FALHA_LLM == texto_final(final)
        assert final["encerrado"] is False

    def test_excecao_dentro_de_ferramenta_vira_instrucao_ao_agente(
        self, executar, monkeypatch
    ):
        from src.tools import credito_tools

        def explode(*_, **__):
            raise RuntimeError("falha inesperada no core bancário")

        monkeypatch.setattr(credito_tools.repo_clientes, "buscar_por_cpf", explode)

        estado = estado_inicial()
        estado.update(
            autenticado=True, cpf=CPF_ANA, nome_cliente="Ana", agente_atual="credito"
        )
        final, _ = executar(
            [
                chamar("consultar_limite_credito"),
                falar("Tive uma instabilidade ao consultar seu limite. "
                      "Posso tentar de novo em instantes?"),
            ],
            estado=estado,
        )
        assert final["encerrado"] is False
        assert isinstance(final["messages"][-1], AIMessage)

    def test_agente_atual_invalido_cai_para_triagem(self, executar):
        estado = estado_inicial()
        estado["agente_atual"] = "agente_que_nao_existe"  # type: ignore[typeddict-item]

        final, _ = executar([falar("Olá! Sou a Ági. Qual é o seu CPF?")], estado=estado)
        assert "CPF" in texto_final(final)


class TestTrilhaDosBastidores:
    """A trilha alimenta o painel de diagnóstico da interface."""

    def _sessao(self, monkeypatch, roteiro):
        from src import graph as modulo_grafo
        from src.atendimento import SessaoAtendimento

        llm = LLMRoteirizado(roteiro)
        monkeypatch.setattr(modulo_grafo, "criar_llm", lambda *a, **k: llm)
        return SessaoAtendimento(thread_id="trilha")

    def test_registra_agente_ferramenta_e_salto(self, bases, monkeypatch):
        sessao = self._sessao(
            monkeypatch,
            [
                falar("Olá! Sou a Ági. Qual é o seu CPF?"),
                chamar("autenticar_cliente", cpf=CPF_ANA, data_nascimento=NASCIMENTO_ANA),
                chamar("transferir_para_credito"),
                chamar("consultar_limite_credito"),
                falar("Ana, seu limite atual é de R$ 3.500,00."),
            ],
        )
        sessao.iniciar()
        sessao.enviar(f"{CPF_ANA}, {NASCIMENTO_ANA} — quero ver meu limite")

        trilha = [(e.tipo, e.nome) for e in sessao.bastidores().trilha_do_turno]
        assert trilha == [
            ("agente", "triagem"),
            ("ferramenta", "autenticar_cliente"),
            ("ferramenta", "transferir_para_credito"),
            ("agente", "credito"),
            ("ferramenta", "consultar_limite_credito"),
        ]

    def test_transferencia_recusada_nao_aparece_como_salto(self, bases, monkeypatch):
        sessao = self._sessao(
            monkeypatch,
            [
                falar("Olá! Sou a Ági. Qual é o seu CPF?"),
                chamar("transferir_para_credito"),
                falar("Antes preciso confirmar sua identidade. Qual é o seu CPF?"),
            ],
        )
        sessao.iniciar()
        sessao.enviar("quero aumentar meu limite")

        trilha = [(e.tipo, e.nome) for e in sessao.bastidores().trilha_do_turno]
        assert trilha == [
            ("agente", "triagem"),
            ("ferramenta", "transferir_para_credito"),
        ]
        assert sessao.bastidores().agente_atual == "triagem"
