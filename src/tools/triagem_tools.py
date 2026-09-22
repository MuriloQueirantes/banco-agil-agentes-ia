"""Ferramentas do Agente de Triagem — autenticação do cliente."""

from __future__ import annotations

from typing import Annotated

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from src.config import MAX_TENTATIVAS_AUTENTICACAO
from src.domain.exceptions import (
    ClienteNaoEncontradoError,
    EntradaInvalidaError,
    ErroDeDadosError,
)
from src.domain.validators import normalizar_cpf, normalizar_data
from src.logging_config import get_logger
from src.repositories import clientes as repo_clientes
from src.state import EstadoAtendimento

logger = get_logger("tools.triagem")


def _resposta(conteudo: str, tool_call_id: str, **atualizacoes) -> Command:
    return Command(
        update={
            **atualizacoes,
            "messages": [ToolMessage(content=conteudo, tool_call_id=tool_call_id)],
        }
    )


@tool("autenticar_cliente")
def autenticar_cliente(
    cpf: str,
    data_nascimento: str,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[EstadoAtendimento, InjectedState],
) -> Command:
    """Valida CPF e data de nascimento contra a base de clientes do banco.

    Chame apenas quando tiver **os dois** dados em mãos. Nunca invente valores
    e nunca declare o cliente autenticado sem chamar esta ferramenta.

    Args:
        cpf: CPF informado pelo cliente, com ou sem pontuação.
        data_nascimento: data de nascimento informada, ex.: "14/03/1988".
    """
    if state.get("autenticado"):
        return _resposta(
            "O cliente já está autenticado. Siga para a identificação do assunto.",
            tool_call_id,
        )

    tentativas_antes = int(state.get("tentativas_autenticacao") or 0)

    # --- Validação de formato: NÃO consome tentativa -----------------------
    # Um CPF digitado errado é erro de digitação, não tentativa de fraude.
    try:
        cpf_normalizado = normalizar_cpf(cpf)
        nascimento = normalizar_data(data_nascimento)
    except EntradaInvalidaError as exc:
        return _resposta(
            f"DADO INVÁLIDO (não conta como tentativa): {exc} "
            "Peça o dado novamente ao cliente de forma gentil.",
            tool_call_id,
        )

    # --- Consulta à base ---------------------------------------------------
    try:
        cliente = repo_clientes.autenticar(cpf_normalizado, nascimento)
    except ClienteNaoEncontradoError:
        tentativas = tentativas_antes + 1
        restantes = MAX_TENTATIVAS_AUTENTICACAO - tentativas

        if restantes <= 0:
            logger.warning("Atendimento encerrado após %s falhas de autenticação", tentativas)
            return _resposta(
                "AUTENTICAÇÃO FALHOU PELA 3ª VEZ. O limite de tentativas acabou. "
                "Informe ao cliente, de forma gentil e sem culpá-lo, que não foi "
                "possível confirmar os dados, oriente-o a procurar um canal oficial "
                "do Banco Ágil e então chame a ferramenta 'encerrar_atendimento'.",
                tool_call_id,
                tentativas_autenticacao=tentativas,
            )

        plural = "tentativas" if restantes > 1 else "tentativa"
        return _resposta(
            f"AUTENTICAÇÃO FALHOU ({tentativas} de {MAX_TENTATIVAS_AUTENTICACAO}). "
            f"Restam {restantes} {plural}. Informe o cliente com cordialidade e "
            "peça novamente CPF e data de nascimento.",
            tool_call_id,
            tentativas_autenticacao=tentativas,
        )
    except ErroDeDadosError as exc:
        logger.exception("Falha ao acessar a base de clientes")
        return _resposta(
            f"ERRO TÉCNICO na base de clientes: {exc} Peça desculpas ao cliente, "
            "explique que houve uma instabilidade momentânea no sistema e sugira "
            "tentar novamente em instantes. Não conte como tentativa.",
            tool_call_id,
        )

    logger.info("Cliente autenticado: %s", cliente.primeiro_nome)
    return _resposta(
        f"AUTENTICAÇÃO CONFIRMADA. Cliente: {cliente.nome} "
        f"(tratar por {cliente.primeiro_nome}). "
        "Cumprimente-o pelo primeiro nome e pergunte como pode ajudar hoje, "
        "mencionando que você pode falar sobre limite de crédito e cotação de moedas.",
        tool_call_id,
        autenticado=True,
        cpf=cliente.cpf,
        nome_cliente=cliente.nome,
        tentativas_autenticacao=0,
    )


FERRAMENTAS_TRIAGEM = {"autenticar_cliente": autenticar_cliente}
