"""Ferramentas do Agente de Entrevista de Crédito — recálculo do score."""

from __future__ import annotations

from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from src.domain.exceptions import (
    ClienteNaoEncontradoError,
    EntradaInvalidaError,
    ErroDeDadosError,
)
from src.domain.models import RespostaEntrevista
from src.domain.scoring import calcular_score
from src.domain.validators import (
    normalizar_booleano,
    normalizar_dependentes,
    normalizar_tipo_emprego,
    normalizar_valor_monetario,
)
from src.logging_config import get_logger
from src.repositories import clientes as repo_clientes
from src.repositories import score_limite as repo_score
from src.state import EstadoAtendimento

logger = get_logger("tools.entrevista")


def _brl(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


@tool("calcular_e_salvar_novo_score")
def calcular_e_salvar_novo_score(
    renda_mensal: float,
    tipo_emprego: str,
    despesas_fixas: float,
    num_dependentes: int,
    tem_dividas: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[EstadoAtendimento, InjectedState],
) -> Command:
    """Calcula o novo score com a fórmula ponderada e o grava em clientes.csv.

    Chame **uma única vez**, somente depois de ter coletado as cinco respostas
    da entrevista. Não presuma nenhum valor que o cliente não tenha informado.

    Args:
        renda_mensal: renda mensal bruta declarada, em reais.
        tipo_emprego: "formal", "autonomo" ou "desempregado".
        despesas_fixas: total de despesas fixas mensais, em reais.
        num_dependentes: quantidade de dependentes.
        tem_dividas: "sim" se possui dívidas ativas, "nao" caso contrário.
    """
    cpf = state.get("cpf")
    if not state.get("autenticado") or not cpf:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            "ERRO DE SESSÃO: não há cliente autenticado. Chame "
                            "'transferir_para_triagem'."
                        ),
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    # --- Normalização das respostas ----------------------------------------
    try:
        resposta = RespostaEntrevista(
            renda_mensal=normalizar_valor_monetario(renda_mensal),
            tipo_emprego=normalizar_tipo_emprego(tipo_emprego),
            despesas_fixas=normalizar_valor_monetario(despesas_fixas),
            num_dependentes=normalizar_dependentes(num_dependentes),
            tem_dividas=normalizar_booleano(tem_dividas),
        )
    except EntradaInvalidaError as exc:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            f"RESPOSTA INVÁLIDA: {exc} Refaça apenas essa pergunta "
                            "ao cliente e chame a ferramenta novamente com todos "
                            "os cinco dados. Nada foi salvo."
                        ),
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    detalhe = calcular_score(resposta)

    # --- Persistência -------------------------------------------------------
    try:
        cliente_antes = repo_clientes.buscar_por_cpf(cpf)
        if cliente_antes is None:
            raise ClienteNaoEncontradoError("Cadastro não localizado.")
        score_anterior = cliente_antes.score
        cliente = repo_clientes.atualizar_score(cpf, detalhe.score)
        novo_teto = repo_score.limite_maximo_para_score(cliente.score)
    except (ErroDeDadosError, ClienteNaoEncontradoError) as exc:
        logger.exception("Falha ao salvar novo score")
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            f"ERRO TÉCNICO ao salvar o score: {exc} Informe o cliente "
                            "que a entrevista foi concluída mas o sistema não conseguiu "
                            "registrar o resultado agora, e peça que tente novamente "
                            "em alguns minutos."
                        ),
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    logger.info(
        "Score recalculado (%s -> %s) | %s",
        score_anterior,
        detalhe.score,
        detalhe.como_texto(),
    )

    direcao = (
        "subiu" if detalhe.score > score_anterior
        else "caiu" if detalhe.score < score_anterior
        else "permaneceu igual"
    )

    return Command(
        update={
            "entrevista_concluida": True,
            "messages": [
                ToolMessage(
                    content=(
                        f"SCORE ATUALIZADO COM SUCESSO. Score anterior: {score_anterior}. "
                        f"Novo score: {detalhe.score} (o score {direcao}). "
                        f"Novo teto de limite autorizado: {_brl(novo_teto)}. "
                        f"Decomposição interna (não repasse ao cliente): {detalhe.como_texto()}. "
                        "Informe ao cliente o novo score em uma frase e, em seguida, "
                        "chame 'transferir_para_credito' para reanalisar o pedido."
                    ),
                    tool_call_id=tool_call_id,
                )
            ],
        }
    )


FERRAMENTAS_ENTREVISTA = {
    "calcular_e_salvar_novo_score": calcular_e_salvar_novo_score
}
