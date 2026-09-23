"""Ferramentas do Agente de Crédito — consulta de limite e pedido de aumento."""

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
from src.domain.validators import normalizar_valor_monetario
from src.logging_config import get_logger
from src.repositories import clientes as repo_clientes
from src.repositories import score_limite as repo_score
from src.repositories import solicitacoes as repo_solicitacoes
from src.repositories.solicitacoes import STATUS_APROVADO, STATUS_REJEITADO
from src.state import EstadoAtendimento

logger = get_logger("tools.credito")

_SEM_SESSAO = (
    "ERRO DE SESSÃO: não há cliente autenticado. Chame 'transferir_para_triagem' "
    "para refazer a autenticação."
)


def _resposta(conteudo: str, tool_call_id: str, **atualizacoes) -> Command:
    return Command(
        update={
            **atualizacoes,
            "messages": [ToolMessage(content=conteudo, tool_call_id=tool_call_id)],
        }
    )


def _brl(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


@tool("consultar_limite_credito")
def consultar_limite_credito(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[EstadoAtendimento, InjectedState],
) -> Command:
    """Consulta o limite de crédito atual e o teto autorizado pelo score.

    Use sempre que o cliente perguntar quanto tem de limite, e também antes de
    registrar um pedido de aumento, para conhecer a situação atual.
    """
    cpf = state.get("cpf")
    if not state.get("autenticado") or not cpf:
        return _resposta(_SEM_SESSAO, tool_call_id)

    try:
        cliente = repo_clientes.buscar_por_cpf(cpf)
        if cliente is None:
            raise ClienteNaoEncontradoError("Cadastro não localizado.")
        teto = repo_score.limite_maximo_para_score(cliente.score)
    except (ErroDeDadosError, ClienteNaoEncontradoError) as exc:
        logger.exception("Falha ao consultar limite")
        return _resposta(
            f"ERRO TÉCNICO ao consultar o limite: {exc} Informe o cliente de forma "
            "clara que o sistema está momentaneamente indisponível e ofereça "
            "tentar novamente ou tratar de outro assunto.",
            tool_call_id,
        )

    margem = teto - cliente.limite_atual
    complemento = (
        f"Pelo score atual, o teto autorizado é {_brl(teto)} — ou seja, há margem "
        f"de até {_brl(margem)} para aumento."
        if margem > 0
        else "O cliente já está no teto autorizado pelo score atual."
    )

    return _resposta(
        f"DADOS DO LIMITE. Limite atual: {_brl(cliente.limite_atual)}. "
        f"Score: {cliente.score}. {complemento} "
        "Informe ao cliente o limite atual de forma direta. Só mencione o teto ou "
        "o score se for útil para a pergunta dele.",
        tool_call_id,
    )


@tool("solicitar_aumento_limite")
def solicitar_aumento_limite(
    novo_limite: float,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[EstadoAtendimento, InjectedState],
) -> Command:
    """Registra formalmente o pedido de aumento e o avalia contra o score.

    O pedido é gravado em `solicitacoes_aumento_limite.csv` com status
    'pendente' e, em seguida, aprovado ou rejeitado conforme a política de
    `score_limite.csv`. Chame apenas quando o cliente informar o valor desejado.

    Args:
        novo_limite: novo limite desejado, em reais.
    """
    cpf = state.get("cpf")
    if not state.get("autenticado") or not cpf:
        return _resposta(_SEM_SESSAO, tool_call_id)

    # --- Validação da entrada ---------------------------------------------
    try:
        valor = normalizar_valor_monetario(novo_limite)
    except EntradaInvalidaError as exc:
        return _resposta(
            f"VALOR INVÁLIDO: {exc} Peça ao cliente que informe o novo limite "
            "desejado em reais. Nenhum pedido foi registrado.",
            tool_call_id,
        )

    try:
        cliente = repo_clientes.buscar_por_cpf(cpf)
        if cliente is None:
            raise ClienteNaoEncontradoError("Cadastro não localizado.")
    except (ErroDeDadosError, ClienteNaoEncontradoError) as exc:
        logger.exception("Falha ao carregar cliente para solicitação")
        return _resposta(
            f"ERRO TÉCNICO: {exc} Avise o cliente sobre a instabilidade e ofereça "
            "tentar novamente mais tarde. Nenhum pedido foi registrado.",
            tool_call_id,
        )

    if valor <= cliente.limite_atual:
        return _resposta(
            f"PEDIDO NÃO REGISTRADO: o valor solicitado ({_brl(valor)}) não é "
            f"maior que o limite atual ({_brl(cliente.limite_atual)}). Explique "
            "isso ao cliente e pergunte qual valor ele gostaria de alcançar.",
            tool_call_id,
        )

    # --- Registro formal (status 'pendente') --------------------------------
    try:
        pedido = repo_solicitacoes.registrar_pedido(
            cpf=cliente.cpf, limite_atual=cliente.limite_atual, novo_limite=valor
        )
    except ErroDeDadosError as exc:
        logger.exception("Falha ao registrar solicitação")
        return _resposta(
            f"ERRO TÉCNICO ao registrar o pedido: {exc} Informe o cliente que não "
            "foi possível protocolar a solicitação agora e ofereça tentar de novo.",
            tool_call_id,
        )

    # --- Avaliação contra a política de score -------------------------------
    try:
        teto = repo_score.limite_maximo_para_score(cliente.score)
        aprovado = valor <= teto
        pedido = repo_solicitacoes.atualizar_status(
            pedido, STATUS_APROVADO if aprovado else STATUS_REJEITADO
        )
    except ErroDeDadosError as exc:
        logger.exception("Falha ao avaliar solicitação")
        return _resposta(
            f"ERRO TÉCNICO na análise: {exc} O pedido ficou registrado como "
            "'pendente' e será avaliado pela equipe. Explique isso ao cliente.",
            tool_call_id,
            status_ultima_solicitacao="pendente",
        )

    if aprovado:
        # O pedido aprovado é efetivado no cadastro. Se a gravação do limite
        # falhar, o pedido continua valendo como 'aprovado' na auditoria e o
        # cliente é avisado de que a atualização aparecerá em instantes — o
        # inverso (dizer que não foi aprovado) seria informação errada.
        try:
            cliente = repo_clientes.atualizar_limite(cliente.cpf, valor)
            efetivado = True
        except (ErroDeDadosError, ClienteNaoEncontradoError):
            logger.exception("Pedido aprovado mas o limite não pôde ser efetivado")
            efetivado = False

        logger.info("Pedido aprovado: %s -> %s", pedido.limite_atual, valor)
        detalhe = (
            f"O limite já está ativo em {_brl(valor)}."
            if efetivado
            else "A atualização do limite está sendo processada e aparecerá em "
                 "instantes; avise o cliente disso."
        )
        return _resposta(
            f"PEDIDO APROVADO. Protocolo {pedido.data_hora_solicitacao}. "
            f"Limite anterior: {_brl(pedido.limite_atual)}. Novo limite: "
            f"{_brl(valor)} (teto do score {cliente.score}: {_brl(teto)}). "
            f"{detalhe} Dê a boa notícia ao cliente e pergunte se ele precisa "
            "de mais alguma coisa.",
            tool_call_id,
            status_ultima_solicitacao=STATUS_APROVADO,
        )

    score_necessario = repo_score.score_minimo_para_limite(valor)
    observacao = (
        f"Seria necessário score a partir de {score_necessario}."
        if score_necessario is not None
        else f"Nenhuma faixa de score autoriza {_brl(valor)}; o teto máximo da política é {_brl(teto)}."
    )

    logger.info("Pedido rejeitado: %s solicitado, teto %s", valor, teto)
    return _resposta(
        f"PEDIDO REJEITADO. Protocolo {pedido.data_hora_solicitacao}. "
        f"O score atual ({cliente.score}) autoriza no máximo {_brl(teto)}, abaixo "
        f"dos {_brl(valor)} pedidos. {observacao} "
        "Comunique a recusa ao cliente com empatia, explique o motivo em uma frase "
        "e OFEREÇA uma entrevista financeira rápida que pode reavaliar o score. "
        "Pergunte se ele deseja fazê-la agora — não transfira antes da resposta.",
        tool_call_id,
        status_ultima_solicitacao=STATUS_REJEITADO,
    )


@tool("consultar_historico_solicitacoes")
def consultar_historico_solicitacoes(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[EstadoAtendimento, InjectedState],
) -> Command:
    """Lista os pedidos de aumento de limite já feitos por este cliente.

    Use quando o cliente perguntar sobre solicitações anteriores ou sobre o
    andamento de um pedido.
    """
    cpf = state.get("cpf")
    if not state.get("autenticado") or not cpf:
        return _resposta(_SEM_SESSAO, tool_call_id)

    pedidos = repo_solicitacoes.listar_por_cpf(cpf)
    if not pedidos:
        return _resposta(
            "HISTÓRICO VAZIO: não há pedidos anteriores de aumento de limite.",
            tool_call_id,
        )

    linhas = "; ".join(
        f"{p.data_hora_solicitacao}: {_brl(p.limite_atual)} -> "
        f"{_brl(p.novo_limite_solicitado)} [{p.status_pedido}]"
        for p in pedidos[-5:]
    )
    return _resposta(f"HISTÓRICO (até 5 mais recentes): {linhas}", tool_call_id)


FERRAMENTAS_CREDITO = {
    "consultar_limite_credito": consultar_limite_credito,
    "solicitar_aumento_limite": solicitar_aumento_limite,
    "consultar_historico_solicitacoes": consultar_historico_solicitacoes,
}
