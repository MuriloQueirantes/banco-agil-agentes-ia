"""Registro declarativo dos agentes: prompt + ferramentas de cada um.

Manter isto como *dados* (e não como quatro funções quase iguais) evita
duplicação: o construtor do grafo itera sobre este registro para criar um nó
por agente e o executor de ferramentas descobre aqui quais tools existem.

Adicionar um quinto agente ao sistema é acrescentar uma entrada nesta lista.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from langchain_core.tools import BaseTool

from src.agents import prompts
from src.tools.cambio_tools import FERRAMENTAS_CAMBIO
from src.tools.credito_tools import FERRAMENTAS_CREDITO
from src.tools.entrevista_tools import FERRAMENTAS_ENTREVISTA
from src.tools.handoff import (
    encerrar_atendimento,
    transferir_para_cambio,
    transferir_para_credito,
    transferir_para_entrevista,
    transferir_para_triagem,
)
from src.tools.triagem_tools import FERRAMENTAS_TRIAGEM


@dataclass(frozen=True)
class DefinicaoAgente:
    nome: str
    descricao: str
    prompt: str
    ferramentas: list[BaseTool] = field(default_factory=list)


AGENTES: dict[str, DefinicaoAgente] = {
    "triagem": DefinicaoAgente(
        nome="triagem",
        descricao="Recepciona, autentica e direciona o cliente",
        prompt=prompts.TRIAGEM,
        ferramentas=[
            *FERRAMENTAS_TRIAGEM.values(),
            transferir_para_credito,
            transferir_para_cambio,
            encerrar_atendimento,
        ],
    ),
    "credito": DefinicaoAgente(
        nome="credito",
        descricao="Consulta limite e processa pedidos de aumento",
        prompt=prompts.CREDITO,
        ferramentas=[
            *FERRAMENTAS_CREDITO.values(),
            transferir_para_entrevista,
            transferir_para_cambio,
            transferir_para_triagem,
            encerrar_atendimento,
        ],
    ),
    "entrevista": DefinicaoAgente(
        nome="entrevista",
        descricao="Conduz a entrevista financeira e recalcula o score",
        prompt=prompts.ENTREVISTA,
        ferramentas=[
            *FERRAMENTAS_ENTREVISTA.values(),
            transferir_para_credito,
            encerrar_atendimento,
        ],
    ),
    "cambio": DefinicaoAgente(
        nome="cambio",
        descricao="Consulta cotação de moedas em tempo real",
        prompt=prompts.CAMBIO,
        ferramentas=[
            *FERRAMENTAS_CAMBIO.values(),
            transferir_para_credito,
            transferir_para_triagem,
            encerrar_atendimento,
        ],
    ),
}

#: Todas as ferramentas do sistema, sem repetição — usado pelo nó executor.
TODAS_AS_FERRAMENTAS: list[BaseTool] = list(
    {
        ferramenta.name: ferramenta
        for definicao in AGENTES.values()
        for ferramenta in definicao.ferramentas
    }.values()
)
