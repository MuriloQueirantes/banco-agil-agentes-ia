"""Ferramentas do Agente de Câmbio — cotação de moedas em tempo real."""

from __future__ import annotations

from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command

from src.config import MOEDAS_SUPORTADAS
from src.domain.exceptions import EntradaInvalidaError, ErroDeIntegracaoError
from src.logging_config import get_logger
from src.services import cambio as servico_cambio

logger = get_logger("tools.cambio")


@tool("consultar_cotacao_moeda")
def consultar_cotacao_moeda(
    moeda: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Busca a cotação atual de uma moeda em reais numa API externa.

    Args:
        moeda: moeda desejada como o cliente falou — "dólar", "USD", "euro",
            "bitcoin" etc. Se ele não especificar, use "dolar".
    """
    try:
        cotacao = servico_cambio.consultar_cotacao(moeda)
    except EntradaInvalidaError as exc:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            f"MOEDA NÃO SUPORTADA: {exc} Informe o cliente e liste "
                            f"as opções disponíveis: {', '.join(sorted(MOEDAS_SUPORTADAS))}."
                        ),
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )
    except ErroDeIntegracaoError as exc:
        logger.exception("Consulta de cotação indisponível")
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            f"SERVIÇO DE COTAÇÃO INDISPONÍVEL: {exc} Peça desculpas ao "
                            "cliente, explique que a fonte de cotação está fora do ar "
                            "no momento, sugira tentar novamente em alguns minutos e "
                            "ofereça ajudar com outro assunto."
                        ),
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=(
                        f"COTAÇÃO OBTIDA: {cotacao.como_texto()}. "
                        "Apresente o valor de compra ao cliente de forma clara, cite "
                        "o horário de atualização e pergunte se pode ajudar em algo mais."
                    ),
                    tool_call_id=tool_call_id,
                )
            ]
        }
    )


FERRAMENTAS_CAMBIO = {"consultar_cotacao_moeda": consultar_cotacao_moeda}
