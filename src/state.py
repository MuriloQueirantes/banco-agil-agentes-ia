"""Estado compartilhado do grafo LangGraph.

Todo dado que precisa sobreviver entre turnos vive aqui — e apenas aqui.
Nada crítico é confiado à "memória" do LLM: se o cliente está autenticado,
quantas tentativas restam e qual agente está no comando são fatos do estado,
não do texto da conversa.
"""

from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

NomeAgente = Literal["triagem", "credito", "entrevista", "cambio"]

AGENTES: tuple[str, ...] = ("triagem", "credito", "entrevista", "cambio")


class EstadoAtendimento(TypedDict, total=False):
    # Histórico da conversa (o reducer add_messages faz o append automático).
    messages: Annotated[list[AnyMessage], add_messages]

    # Qual agente responde no próximo turno. É o mecanismo de handoff:
    # as tools de transferência alteram este campo e o roteador do grafo
    # encaminha a execução — sem que o cliente perceba a troca.
    agente_atual: NomeAgente

    # --- Autenticação (Agente de Triagem) ---
    autenticado: bool
    tentativas_autenticacao: int
    cpf: str | None
    nome_cliente: str | None

    # --- Crédito ---
    # Status da última solicitação de aumento: alimenta a regra de oferecer a
    # entrevista quando o pedido é rejeitado.
    status_ultima_solicitacao: str | None
    entrevista_concluida: bool

    # --- Controle de ciclo de vida ---
    encerrado: bool
    motivo_encerramento: str | None


def estado_inicial() -> EstadoAtendimento:
    return {
        "messages": [],
        "agente_atual": "triagem",
        "autenticado": False,
        "tentativas_autenticacao": 0,
        "cpf": None,
        "nome_cliente": None,
        "status_ultima_solicitacao": None,
        "entrevista_concluida": False,
        "encerrado": False,
        "motivo_encerramento": None,
    }
