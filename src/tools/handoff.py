"""Ferramentas de transferência entre agentes e de encerramento.

O handoff é feito por *tool call*: o agente chama `transferir_para_X`, a tool
devolve um `Command` que altera `agente_atual` no estado, e o roteador do grafo
entrega o turno ao novo agente **dentro da mesma volta** — o cliente recebe uma
única resposta e não percebe a troca, como exige o enunciado.

O `ToolMessage` devolvido é uma instrução interna para o agente que assume,
nunca um texto exibido ao cliente.
"""

from __future__ import annotations

from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from src.state import EstadoAtendimento

_NAO_AUTENTICADO = (
    "BLOQUEADO: o cliente ainda não foi autenticado. Permaneça na triagem e "
    "conclua a verificação de CPF e data de nascimento antes de transferir."
)


def _transferir(
    destino: str, instrucao: str, tool_call_id: str, estado: EstadoAtendimento
) -> Command:
    if not estado.get("autenticado"):
        return Command(
            update={
                "messages": [
                    ToolMessage(content=_NAO_AUTENTICADO, tool_call_id=tool_call_id)
                ]
            }
        )
    return Command(
        update={
            "agente_atual": destino,
            "messages": [ToolMessage(content=instrucao, tool_call_id=tool_call_id)],
        }
    )


@tool("transferir_para_credito")
def transferir_para_credito(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[EstadoAtendimento, InjectedState],
) -> Command:
    """Encaminha o atendimento para o especialista em limite de crédito.

    Use quando o cliente quiser consultar o limite disponível, pedir aumento de
    limite ou falar sobre cartão/crédito em geral.
    """
    return _transferir(
        "credito",
        "CONTEXTO INTERNO: você agora é o especialista em crédito. Atenda a "
        "demanda do cliente sobre limite sem se reapresentar e sem mencionar "
        "qualquer transferência.",
        tool_call_id,
        state,
    )


@tool("transferir_para_cambio")
def transferir_para_cambio(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[EstadoAtendimento, InjectedState],
) -> Command:
    """Encaminha o atendimento para o especialista em câmbio.

    Use quando o cliente perguntar sobre cotação de moedas (dólar, euro etc.).
    """
    return _transferir(
        "cambio",
        "CONTEXTO INTERNO: você agora é o especialista em câmbio. Consulte a "
        "cotação pedida sem se reapresentar e sem mencionar transferências.",
        tool_call_id,
        state,
    )


@tool("transferir_para_entrevista")
def transferir_para_entrevista(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[EstadoAtendimento, InjectedState],
) -> Command:
    """Encaminha o cliente para a entrevista financeira de recálculo de score.

    Use somente depois de o cliente aceitar explicitamente fazer a entrevista.
    """
    return _transferir(
        "entrevista",
        "CONTEXTO INTERNO: você agora conduz a entrevista financeira. Faça a "
        "primeira pergunta diretamente, sem se reapresentar.",
        tool_call_id,
        state,
    )


@tool("transferir_para_triagem")
def transferir_para_triagem(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[EstadoAtendimento, InjectedState],
) -> Command:
    """Devolve o atendimento à triagem para identificar um novo assunto.

    Use quando o cliente mudar para um assunto fora da sua especialidade.
    """
    return _transferir(
        "triagem",
        "CONTEXTO INTERNO: você voltou a ser a triagem. Identifique o novo "
        "assunto do cliente e encaminhe. Não se reapresente.",
        tool_call_id,
        state,
    )


@tool("encerrar_atendimento")
def encerrar_atendimento(
    mensagem_de_despedida: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    motivo: str = "solicitado pelo cliente",
) -> Command:
    """Finaliza o atendimento e encerra o loop de execução.

    Chame sempre que o cliente pedir para encerrar, se despedir ("tchau",
    "obrigado, é só isso") ou quando o atendimento chegar naturalmente ao fim.

    Args:
        mensagem_de_despedida: texto cordial de despedida que será exibido ao
            cliente como última mensagem do atendimento.
        motivo: registro interno do motivo do encerramento.
    """
    return Command(
        update={
            "encerrado": True,
            "motivo_encerramento": motivo,
            "messages": [
                ToolMessage(
                    content=(
                        "ATENDIMENTO ENCERRADO. Responda ao cliente exatamente com "
                        f"esta despedida e nada mais: {mensagem_de_despedida}"
                    ),
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )


FERRAMENTAS_HANDOFF = {
    "transferir_para_credito": transferir_para_credito,
    "transferir_para_cambio": transferir_para_cambio,
    "transferir_para_entrevista": transferir_para_entrevista,
    "transferir_para_triagem": transferir_para_triagem,
    "encerrar_atendimento": encerrar_atendimento,
}
