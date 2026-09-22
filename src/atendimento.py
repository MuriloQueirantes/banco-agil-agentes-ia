"""Fachada de atendimento — a API que a UI e a CLI consomem.

Encapsula o grafo para que as interfaces não precisem conhecer LangGraph:
elas apenas criam uma `SessaoAtendimento`, chamam `iniciar()` e `enviar()`.
Cada sessão tem seu próprio `thread_id`, então o checkpointer mantém as
conversas isoladas umas das outras.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from src.agents.definicoes import AGENTES
from src.domain.models import SolicitacaoAumento
from src.domain.validators import mascarar_cpf
from src.graph import construir_grafo
from src.mensagens import texto_de
from src.repositories.solicitacoes import listar_por_cpf
from src.logging_config import get_logger
from src.state import estado_inicial

logger = get_logger("atendimento")

#: Gatilho interno do primeiro turno. Não é exibido na interface: serve apenas
#: para que o agente de triagem produza a saudação inicial sem que o cliente
#: precise falar primeiro.
ABERTURA = "(o cliente acabou de abrir a janela de atendimento)"

#: Teto de voltas agente↔ferramenta num mesmo turno. Protege contra um modelo
#: que entre em laço de transferências.
LIMITE_DE_RECURSAO = 25

RESPOSTA_VAZIA = (
    "Desculpe, não consegui formular uma resposta agora. Pode repetir, por favor?"
)


@dataclass(frozen=True, slots=True)
class EventoDaTrilha:
    """Um passo do percurso interno de um turno.

    `tipo` é "agente" quando o turno entra num especialista e "ferramenta"
    quando uma ação é executada. É o que alimenta o painel de bastidores:
    o cliente vê uma conversa contínua, o avaliador vê o caminho percorrido.
    """

    tipo: str
    nome: str


@dataclass(frozen=True, slots=True)
class Bastidores:
    """Estado interno da sessão, para o painel de diagnóstico da UI."""

    agente_atual: str
    especialidade: str
    autenticado: bool
    cliente: str | None
    cpf_mascarado: str | None
    tentativas_autenticacao: int
    status_ultima_solicitacao: str | None
    entrevista_concluida: bool
    encerrado: bool
    ferramentas_do_turno: list[str]
    trilha_do_turno: list[EventoDaTrilha]


class SessaoAtendimento:
    """Uma conversa com o Banco Ágil, do "olá" ao encerramento."""

    def __init__(self, thread_id: str | None = None, checkpointer: Any = None) -> None:
        self.thread_id = thread_id or str(uuid.uuid4())
        self._grafo = construir_grafo(checkpointer or MemorySaver())
        self._config = {
            "configurable": {"thread_id": self.thread_id},
            "recursion_limit": LIMITE_DE_RECURSAO,
        }
        self._estado: dict[str, Any] = estado_inicial()
        self._iniciada = False
        self._trilha_do_turno: list[EventoDaTrilha] = []
        logger.info("Sessão criada: %s", self.thread_id)

    # -- ciclo de vida -----------------------------------------------------
    def iniciar(self) -> str:
        """Dispara a saudação inicial do agente de triagem."""
        if self._iniciada:
            return self.ultima_resposta
        self._iniciada = True
        return self._rodar(ABERTURA)

    def enviar(self, mensagem_do_cliente: str) -> str:
        """Processa um turno e devolve a fala do agente."""
        if self.encerrado:
            return "Este atendimento já foi encerrado. Inicie um novo para continuar."
        if not self._iniciada:
            self._iniciada = True
        return self._rodar(mensagem_do_cliente)

    # -- execução ----------------------------------------------------------
    def _rodar(self, texto: str) -> str:
        partida = (
            self._estado.get("agente_atual") or "triagem",
            bool(self._estado.get("autenticado")),
        )
        entrada = {**self._estado, "messages": [HumanMessage(content=texto)]}

        try:
            self._estado = self._grafo.invoke(entrada, config=self._config)
        except Exception:
            # Falha estrutural (ex.: limite de recursão). A sessão continua de
            # pé e o cliente recebe uma resposta em vez de uma exceção.
            logger.exception("Falha ao executar o turno na sessão %s", self.thread_id)
            return (
                "Desculpe, tive um problema técnico ao processar seu pedido. "
                "Pode tentar novamente, por favor?"
            )

        self._trilha_do_turno = self._montar_trilha(*partida)
        return self.ultima_resposta

    def _ferramentas_do_turno(self) -> list[str]:
        """Ferramentas chamadas desde a última fala do cliente, em ordem."""
        nomes: list[str] = []
        for mensagem in reversed(self._estado.get("messages", [])):
            if isinstance(mensagem, HumanMessage):
                break
            if isinstance(mensagem, AIMessage) and mensagem.tool_calls:
                nomes.extend(
                    chamada["name"] for chamada in reversed(mensagem.tool_calls)
                )
        return list(reversed(nomes))

    def _montar_trilha(
        self, agente_de_partida: str, autenticado_na_partida: bool
    ) -> list[EventoDaTrilha]:
        """Reconstrói o percurso do turno: por onde passou e o que executou.

        Uma transferência pedida antes da autenticação é recusada pela própria
        ferramenta e não muda o agente. Reproduzimos essa regra aqui para que a
        trilha mostre o caminho real, não o caminho pretendido pelo modelo.
        """
        trilha = [EventoDaTrilha("agente", agente_de_partida)]
        autenticado = autenticado_na_partida

        for ferramenta in self._ferramentas_do_turno():
            trilha.append(EventoDaTrilha("ferramenta", ferramenta))

            if ferramenta == "autenticar_cliente":
                autenticado = bool(self._estado.get("autenticado"))
            elif ferramenta.startswith("transferir_para_") and autenticado:
                trilha.append(
                    EventoDaTrilha(
                        "agente", ferramenta.removeprefix("transferir_para_")
                    )
                )

        return trilha

    # -- leitura -----------------------------------------------------------
    @property
    def ultima_resposta(self) -> str:
        for mensagem in reversed(self._estado.get("messages", [])):
            if isinstance(mensagem, AIMessage):
                texto = texto_de(mensagem)
                if texto:
                    return texto
        return RESPOSTA_VAZIA

    @property
    def encerrado(self) -> bool:
        return bool(self._estado.get("encerrado"))

    @property
    def autenticado(self) -> bool:
        return bool(self._estado.get("autenticado"))

    def pedidos_do_cliente(self) -> list[SolicitacaoAumento]:
        """Pedidos de aumento já registrados para o cliente em sessão."""
        cpf = self._estado.get("cpf")
        return listar_por_cpf(cpf) if cpf else []

    def bastidores(self) -> Bastidores:
        agente = self._estado.get("agente_atual") or "triagem"
        cpf = self._estado.get("cpf")
        return Bastidores(
            agente_atual=agente,
            especialidade=AGENTES[agente].descricao if agente in AGENTES else "—",
            autenticado=self.autenticado,
            cliente=self._estado.get("nome_cliente"),
            cpf_mascarado=mascarar_cpf(cpf) if cpf else None,
            tentativas_autenticacao=int(
                self._estado.get("tentativas_autenticacao") or 0
            ),
            status_ultima_solicitacao=self._estado.get("status_ultima_solicitacao"),
            entrevista_concluida=bool(self._estado.get("entrevista_concluida")),
            encerrado=self.encerrado,
            ferramentas_do_turno=[
                e.nome for e in self._trilha_do_turno if e.tipo == "ferramenta"
            ],
            trilha_do_turno=list(self._trilha_do_turno),
        )
