"""Acesso a `solicitacoes_aumento_limite.csv` — trilha de auditoria.

O enunciado pede que o pedido seja **registrado antes** da análise, com as
colunas exatas abaixo. Por isso o fluxo é: grava `pendente` -> avalia o score
-> atualiza a mesma linha para `aprovado`/`rejeitado`. O status intermediário
fica visível no arquivo caso a avaliação falhe no meio do caminho.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.config import SOLICITACOES_CSV
from src.domain.exceptions import ErroDeDadosError
from src.domain.models import SolicitacaoAumento
from src.domain.validators import somente_digitos
from src.logging_config import get_logger
from src.repositories.csv_base import acrescentar_linha, escrever_csv, ler_csv

logger = get_logger("repositories.solicitacoes")

COLUNAS = [
    "cpf_cliente",
    "data_hora_solicitacao",
    "limite_atual",
    "novo_limite_solicitado",
    "status_pedido",
]

STATUS_PENDENTE = "pendente"
STATUS_APROVADO = "aprovado"
STATUS_REJEITADO = "rejeitado"


def _agora_iso() -> str:
    """Timestamp ISO 8601 com milissegundos.

    A precisão de milissegundos não é estética: o timestamp faz parte da chave
    que identifica a linha em `atualizar_status`. Com precisão de segundos,
    dois pedidos do mesmo cliente feitos na mesma conversa colidiriam e o
    status seria gravado na linha errada.
    """
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def registrar_pedido(
    cpf: str, limite_atual: float, novo_limite: float
) -> SolicitacaoAumento:
    """Cria o pedido formal com status 'pendente'."""
    pedido = SolicitacaoAumento(
        cpf_cliente=somente_digitos(cpf).zfill(11),
        data_hora_solicitacao=_agora_iso(),
        limite_atual=round(float(limite_atual), 2),
        novo_limite_solicitado=round(float(novo_limite), 2),
        status_pedido=STATUS_PENDENTE,
    )
    acrescentar_linha(
        SOLICITACOES_CSV,
        COLUNAS,
        {
            "cpf_cliente": pedido.cpf_cliente,
            "data_hora_solicitacao": pedido.data_hora_solicitacao,
            "limite_atual": f"{pedido.limite_atual:.2f}",
            "novo_limite_solicitado": f"{pedido.novo_limite_solicitado:.2f}",
            "status_pedido": pedido.status_pedido,
        },
    )
    logger.info(
        "Pedido registrado: cpf=***%s novo_limite=%.2f",
        pedido.cpf_cliente[-4:],
        pedido.novo_limite_solicitado,
    )
    return pedido


def atualizar_status(pedido: SolicitacaoAumento, novo_status: str) -> SolicitacaoAumento:
    """Atualiza o status da linha identificada por CPF + timestamp."""
    if novo_status not in (STATUS_PENDENTE, STATUS_APROVADO, STATUS_REJEITADO):
        raise ErroDeDadosError(f"Status de pedido desconhecido: '{novo_status}'.")

    linhas = ler_csv(SOLICITACOES_CSV)
    atualizada = False
    # Percorremos de trás para frente: em caso de empate improvável na chave,
    # o pedido mais recente é o que está sendo avaliado agora.
    for linha in reversed(linhas):
        mesmo_cpf = (
            somente_digitos(linha.get("cpf_cliente", "")).zfill(11)
            == pedido.cpf_cliente
        )
        mesmo_instante = (
            linha.get("data_hora_solicitacao") == pedido.data_hora_solicitacao
        )
        mesmo_valor = (
            linha.get("novo_limite_solicitado", "").strip()
            == f"{pedido.novo_limite_solicitado:.2f}"
        )
        if mesmo_cpf and mesmo_instante and mesmo_valor:
            linha["status_pedido"] = novo_status
            atualizada = True
            break

    if not atualizada:
        raise ErroDeDadosError(
            "Não localizei a solicitação registrada para atualizar o status."
        )

    escrever_csv(SOLICITACOES_CSV, COLUNAS, linhas)
    logger.info(
        "Pedido de ***%s atualizado para '%s'", pedido.cpf_cliente[-4:], novo_status
    )
    return SolicitacaoAumento(
        cpf_cliente=pedido.cpf_cliente,
        data_hora_solicitacao=pedido.data_hora_solicitacao,
        limite_atual=pedido.limite_atual,
        novo_limite_solicitado=pedido.novo_limite_solicitado,
        status_pedido=novo_status,
    )


def listar_por_cpf(cpf: str) -> list[SolicitacaoAumento]:
    alvo = somente_digitos(cpf).zfill(11)
    try:
        linhas = ler_csv(SOLICITACOES_CSV)
    except ErroDeDadosError:
        return []
    return [
        SolicitacaoAumento(
            cpf_cliente=somente_digitos(l.get("cpf_cliente", "")).zfill(11),
            data_hora_solicitacao=l.get("data_hora_solicitacao", ""),
            limite_atual=float(l.get("limite_atual") or 0),
            novo_limite_solicitado=float(l.get("novo_limite_solicitado") or 0),
            status_pedido=l.get("status_pedido", ""),
        )
        for l in linhas
        if somente_digitos(l.get("cpf_cliente", "")).zfill(11) == alvo
    ]
