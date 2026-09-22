"""Construção do grafo de atendimento (LangGraph).

Topologia
---------

                      ┌──────────────────────────────┐
                      │  roteador de entrada (state) │
                      └──────────────┬───────────────┘
              ┌──────────────┬───────┴───────┬──────────────┐
              ▼              ▼               ▼              ▼
         [ triagem ]   [ credito ]    [ entrevista ]   [ cambio ]
              └──────────────┴───────┬───────┴──────────────┘
                                     │ há tool_calls?
                          não ───────┤────── sim
                           │         ▼
                           │   [ ferramentas ]  (ToolNode)
                           │         │
                           │         ├── encerrado? ──► END
                           ▼         └── volta para o agente indicado
                          END                  por `agente_atual`
                   (aguarda o cliente)

Três decisões estruturais:

1. **Um nó por agente, com prompt e ferramentas próprios.** É o que garante o
   "nenhum agente pode atuar fora do seu escopo": o agente de câmbio sequer
   possui a ferramenta que grava pedido de aumento de limite.

2. **Handoff pelo estado, não por `goto`.** As tools de transferência apenas
   escrevem `agente_atual`; quem decide o próximo nó é uma aresta condicional.
   O roteamento fica num lugar só, legível e testável sem LLM.

3. **O grafo termina o turno quando o agente responde sem tool call.** Isso é o
   que torna a transferência invisível: triagem → transferência → crédito
   acontece dentro de uma única volta, e o cliente recebe só a resposta final.
"""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import AIMessage, AnyMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from src.agents.definicoes import AGENTES, TODAS_AS_FERRAMENTAS
from src.config import MAX_TENTATIVAS_AUTENTICACAO
from src.domain.validators import mascarar_cpf
from src.llm import criar_llm
from src.logging_config import get_logger
from src.state import EstadoAtendimento, estado_inicial

logger = get_logger("graph")

NO_FERRAMENTAS = "ferramentas"

#: Quantas mensagens de histórico são enviadas ao LLM a cada turno. Mantém o
#: custo previsível em conversas longas sem perder o contexto recente.
JANELA_DE_MENSAGENS = 40

MENSAGEM_FALHA_LLM = (
    "Desculpe, tive uma instabilidade momentânea aqui e não consegui processar "
    "sua mensagem. Pode repetir, por favor?"
)


# --------------------------------------------------------------------------
# Contexto dinâmico injetado no prompt
# --------------------------------------------------------------------------
def _contexto_da_sessao(state: EstadoAtendimento) -> str:
    """Espelha o estado real da sessão dentro do prompt do sistema.

    Sem isso o modelo precisaria reconstruir da conversa se o cliente está
    autenticado ou quantas tentativas restam — exatamente o tipo de fato que
    não pode depender da interpretação do LLM.
    """
    linhas = ["\n## Estado atual da sessão (informação interna, não repasse)"]

    if state.get("autenticado"):
        linhas.append(f"- Cliente AUTENTICADO: {state.get('nome_cliente')}")
        linhas.append(f"- CPF em sessão: {mascarar_cpf(state.get('cpf') or '')}")
    else:
        usadas = int(state.get("tentativas_autenticacao") or 0)
        linhas.append("- Cliente NÃO autenticado.")
        linhas.append(
            f"- Tentativas de autenticação usadas: {usadas} de "
            f"{MAX_TENTATIVAS_AUTENTICACAO}."
        )

    status = state.get("status_ultima_solicitacao")
    if status:
        linhas.append(f"- Status do último pedido de aumento de limite: {status}.")
    if state.get("entrevista_concluida"):
        linhas.append(
            "- A entrevista financeira JÁ foi realizada nesta sessão. Não a "
            "ofereça novamente; o score já está atualizado."
        )

    return "\n".join(linhas)


def _janela(mensagens: list[AnyMessage]) -> list[AnyMessage]:
    """Últimas N mensagens, sem cortar um par tool_call / ToolMessage ao meio.

    Uma `ToolMessage` órfã (sem a `AIMessage` que a originou) é rejeitada pela
    API do Gemini, então recuamos o corte até a fronteira segura mais próxima.
    """
    if len(mensagens) <= JANELA_DE_MENSAGENS:
        return mensagens

    inicio = len(mensagens) - JANELA_DE_MENSAGENS
    while inicio > 0 and isinstance(mensagens[inicio], ToolMessage):
        inicio -= 1
    return mensagens[inicio:]


# --------------------------------------------------------------------------
# Nós dos agentes
# --------------------------------------------------------------------------
def _criar_no_agente(nome_agente: str):
    definicao = AGENTES[nome_agente]

    def no(state: EstadoAtendimento) -> dict:
        prompt = definicao.prompt + _contexto_da_sessao(state)
        mensagens = [SystemMessage(content=prompt), *_janela(state.get("messages", []))]

        try:
            llm = criar_llm().bind_tools(definicao.ferramentas)
            resposta = llm.invoke(mensagens)
        except Exception:
            # Rede fora, rate limit, chave inválida: a conversa não pode cair.
            # Registramos o stack trace e devolvemos uma fala de contingência.
            logger.exception("Falha ao invocar o LLM no agente '%s'", nome_agente)
            return {"messages": [AIMessage(content=MENSAGEM_FALHA_LLM)]}

        if logger.isEnabledFor(10):  # DEBUG
            chamadas = [c["name"] for c in (resposta.tool_calls or [])]
            logger.debug("[%s] tool_calls=%s", nome_agente, chamadas or "nenhuma")

        return {"messages": [resposta]}

    no.__name__ = f"no_{nome_agente}"
    return no


# --------------------------------------------------------------------------
# Roteadores
# --------------------------------------------------------------------------
def _agente_valido(state: EstadoAtendimento) -> str:
    nome = state.get("agente_atual") or "triagem"
    if nome not in AGENTES:
        logger.warning("Agente desconhecido '%s'; usando triagem.", nome)
        return "triagem"
    return nome


def rotear_entrada(state: EstadoAtendimento) -> str:
    """START → o agente que detém o turno."""
    if state.get("encerrado"):
        return END
    return _agente_valido(state)


def rotear_apos_agente(state: EstadoAtendimento) -> Literal["ferramentas", "__end__"]:
    """Agente → ferramentas (se pediu) ou fim do turno (aguarda o cliente)."""
    mensagens = state.get("messages", [])
    ultima = mensagens[-1] if mensagens else None
    if isinstance(ultima, AIMessage) and ultima.tool_calls:
        return NO_FERRAMENTAS
    return END


def rotear_apos_ferramentas(state: EstadoAtendimento) -> str:
    """Ferramentas → agente indicado pelo estado (possivelmente outro)."""
    return _agente_valido(state)


# --------------------------------------------------------------------------
# Construção
# --------------------------------------------------------------------------
def _mensagem_de_erro_de_ferramenta(exc: Exception) -> str:
    """Rede de segurança: exceção não prevista dentro de uma tool.

    Os erros *esperados* já são tratados dentro de cada ferramenta e viram
    instruções em português. Isto aqui cobre o imprevisto — o agente recebe
    um texto acionável em vez de o grafo abortar.
    """
    logger.exception("Exceção não tratada em ferramenta: %s", exc)
    return (
        "ERRO TÉCNICO INESPERADO ao executar a operação. Peça desculpas ao "
        "cliente pela instabilidade, não repita a tentativa automaticamente e "
        "ofereça continuar com outro assunto ou tentar de novo em instantes."
    )


def construir_grafo(checkpointer=None):
    """Monta e compila o grafo de atendimento."""
    construtor = StateGraph(EstadoAtendimento)

    for nome in AGENTES:
        construtor.add_node(nome, _criar_no_agente(nome))

    construtor.add_node(
        NO_FERRAMENTAS,
        ToolNode(
            TODAS_AS_FERRAMENTAS,
            handle_tool_errors=_mensagem_de_erro_de_ferramenta,
        ),
    )

    destinos_agentes = {nome: nome for nome in AGENTES}

    construtor.add_conditional_edges(
        START, rotear_entrada, {**destinos_agentes, END: END}
    )

    for nome in AGENTES:
        construtor.add_conditional_edges(
            nome,
            rotear_apos_agente,
            {NO_FERRAMENTAS: NO_FERRAMENTAS, END: END},
        )

    construtor.add_conditional_edges(
        NO_FERRAMENTAS, rotear_apos_ferramentas, destinos_agentes
    )

    return construtor.compile(checkpointer=checkpointer or MemorySaver())


__all__ = ["construir_grafo", "estado_inicial", "EstadoAtendimento"]
