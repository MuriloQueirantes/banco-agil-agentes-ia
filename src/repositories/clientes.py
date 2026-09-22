"""Acesso a `clientes.csv` — autenticação e atualização de score."""

from __future__ import annotations

from datetime import date

from src.config import CLIENTES_CSV
from src.domain.exceptions import ClienteNaoEncontradoError, ErroDeDadosError
from src.domain.models import Cliente
from src.domain.validators import mascarar_cpf, normalizar_cpf, somente_digitos
from src.logging_config import get_logger
from src.repositories.csv_base import (
    campo_float,
    campo_int,
    escrever_csv,
    exigir_colunas,
    ler_csv,
)

logger = get_logger("repositories.clientes")

COLUNAS = ["cpf", "nome", "data_nascimento", "limite_atual", "score"]
_OBRIGATORIAS = set(COLUNAS)


def _para_cliente(linha: dict[str, str]) -> Cliente:
    try:
        nascimento = date.fromisoformat(linha["data_nascimento"].strip())
    except ValueError as exc:
        raise ErroDeDadosError(
            "Data de nascimento em formato inesperado na base de clientes "
            f"(esperado AAAA-MM-DD, recebido '{linha.get('data_nascimento')}')."
        ) from exc

    return Cliente(
        cpf=somente_digitos(linha["cpf"]).zfill(11),
        nome=linha["nome"].strip(),
        data_nascimento=nascimento,
        limite_atual=campo_float(linha, "limite_atual", CLIENTES_CSV.name),
        score=campo_int(linha, "score", CLIENTES_CSV.name),
    )


def listar_clientes() -> list[Cliente]:
    linhas = ler_csv(CLIENTES_CSV)
    exigir_colunas(linhas, _OBRIGATORIAS, CLIENTES_CSV.name)
    return [_para_cliente(linha) for linha in linhas]


def buscar_por_cpf(cpf: str) -> Cliente | None:
    alvo = somente_digitos(cpf).zfill(11)
    return next((c for c in listar_clientes() if c.cpf == alvo), None)


def autenticar(cpf: str, data_nascimento: date) -> Cliente:
    """Confere CPF **e** data de nascimento. Levanta erro se não bater.

    A mensagem de falha é a mesma para "CPF inexistente" e "data errada",
    para não revelar quais CPFs existem na base (enumeração de contas).
    """
    cpf_normalizado = normalizar_cpf(cpf)
    cliente = buscar_por_cpf(cpf_normalizado)

    if cliente is None or cliente.data_nascimento != data_nascimento:
        logger.info(
            "Autenticação negada para CPF %s", mascarar_cpf(cpf_normalizado)
        )
        raise ClienteNaoEncontradoError(
            "Os dados informados não conferem com os nossos registros."
        )

    logger.info("Autenticação concedida para CPF %s", mascarar_cpf(cliente.cpf))
    return cliente


def atualizar_score(cpf: str, novo_score: int) -> Cliente:
    """Persiste o novo score preservando as demais colunas do arquivo."""
    alvo = somente_digitos(cpf).zfill(11)
    linhas = ler_csv(CLIENTES_CSV)
    exigir_colunas(linhas, _OBRIGATORIAS, CLIENTES_CSV.name)

    encontrado = False
    for linha in linhas:
        if somente_digitos(linha["cpf"]).zfill(11) == alvo:
            linha["score"] = str(int(novo_score))
            encontrado = True
            break

    if not encontrado:
        raise ClienteNaoEncontradoError(
            "Não localizei o cadastro para atualizar o score."
        )

    colunas = list(linhas[0].keys()) if linhas else COLUNAS
    escrever_csv(CLIENTES_CSV, colunas, linhas)
    logger.info(
        "Score do CPF %s atualizado para %s", mascarar_cpf(alvo), novo_score
    )

    atualizado = buscar_por_cpf(alvo)
    if atualizado is None:  # pragma: no cover - inconsistência improvável
        raise ErroDeDadosError("Falha ao reler o cadastro após a atualização.")
    return atualizado
