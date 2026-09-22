"""Utilitários de acesso a CSV.

Decisões conscientes:

* **`csv` da biblioteca padrão, não pandas.** O CPF é uma *string* que pode
  começar com zero (`08301661305`). O pandas infere `int64` e destrói o zero à
  esquerda silenciosamente — um bug de autenticação difícil de achar. Com o
  módulo `csv` todo campo chega como `str` e a conversão é explícita.
* **Escrita atômica.** Gravamos num arquivo temporário no mesmo diretório e
  usamos `os.replace`, que é atômico no POSIX. Se o processo morrer no meio de
  uma atualização de score, `clientes.csv` nunca fica truncado.
* **Lock por processo.** O Streamlit atende sessões em threads distintas; o
  lock evita que duas escritas concorrentes se sobreponham.
"""

from __future__ import annotations

import csv
import os
import tempfile
import threading
from pathlib import Path
from typing import Iterable

from src.domain.exceptions import ErroDeDadosError
from src.logging_config import get_logger

logger = get_logger("repositories.csv")

_LOCK_ESCRITA = threading.RLock()


def ler_csv(caminho: Path) -> list[dict[str, str]]:
    """Lê um CSV em lista de dicts. Erros viram ErroDeDadosError."""
    try:
        with caminho.open("r", encoding="utf-8", newline="") as arquivo:
            leitor = csv.DictReader(arquivo)
            if leitor.fieldnames is None:
                raise ErroDeDadosError(f"'{caminho.name}' está vazio ou sem cabeçalho.")
            return [
                {(k or "").strip(): (v or "").strip() for k, v in linha.items()}
                for linha in leitor
            ]
    except FileNotFoundError as exc:
        logger.error("Base não encontrada: %s", caminho)
        raise ErroDeDadosError(
            f"A base de dados '{caminho.name}' não foi encontrada."
        ) from exc
    except UnicodeDecodeError as exc:
        logger.error("Encoding inválido em %s: %s", caminho, exc)
        raise ErroDeDadosError(
            f"A base '{caminho.name}' não está em UTF-8 e não pôde ser lida."
        ) from exc
    except csv.Error as exc:
        logger.error("CSV malformado em %s: %s", caminho, exc)
        raise ErroDeDadosError(f"A base '{caminho.name}' está malformada.") from exc
    except OSError as exc:
        logger.error("Falha de I/O ao ler %s: %s", caminho, exc)
        raise ErroDeDadosError(f"Não foi possível ler '{caminho.name}'.") from exc


def escrever_csv(
    caminho: Path, colunas: list[str], linhas: Iterable[dict[str, object]]
) -> None:
    """Reescreve o arquivo inteiro de forma atômica."""
    with _LOCK_ESCRITA:
        try:
            caminho.parent.mkdir(parents=True, exist_ok=True)
            fd, temporario = tempfile.mkstemp(
                dir=str(caminho.parent), prefix=f".{caminho.name}.", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8", newline="") as arquivo:
                    escritor = csv.DictWriter(arquivo, fieldnames=colunas)
                    escritor.writeheader()
                    for linha in linhas:
                        escritor.writerow(linha)
                    arquivo.flush()
                    os.fsync(arquivo.fileno())
                os.replace(temporario, caminho)
            except BaseException:
                Path(temporario).unlink(missing_ok=True)
                raise
        except OSError as exc:
            logger.error("Falha de I/O ao escrever %s: %s", caminho, exc)
            raise ErroDeDadosError(
                f"Não foi possível gravar em '{caminho.name}'."
            ) from exc


def acrescentar_linha(
    caminho: Path, colunas: list[str], linha: dict[str, object]
) -> None:
    """Acrescenta uma linha, criando o arquivo com cabeçalho se necessário."""
    with _LOCK_ESCRITA:
        try:
            caminho.parent.mkdir(parents=True, exist_ok=True)
            precisa_cabecalho = (
                not caminho.exists() or caminho.stat().st_size == 0
            )
            with caminho.open("a", encoding="utf-8", newline="") as arquivo:
                escritor = csv.DictWriter(arquivo, fieldnames=colunas)
                if precisa_cabecalho:
                    escritor.writeheader()
                escritor.writerow(linha)
        except OSError as exc:
            logger.error("Falha de I/O ao acrescentar em %s: %s", caminho, exc)
            raise ErroDeDadosError(
                f"Não foi possível registrar os dados em '{caminho.name}'."
            ) from exc


def campo_float(linha: dict[str, str], campo: str, arquivo: str) -> float:
    bruto = (linha.get(campo) or "").replace(",", ".").strip()
    try:
        return float(bruto)
    except ValueError as exc:
        raise ErroDeDadosError(
            f"Valor inválido na coluna '{campo}' de '{arquivo}': '{bruto}'."
        ) from exc


def campo_int(linha: dict[str, str], campo: str, arquivo: str) -> int:
    bruto = (linha.get(campo) or "").strip()
    try:
        return int(float(bruto))
    except ValueError as exc:
        raise ErroDeDadosError(
            f"Valor inválido na coluna '{campo}' de '{arquivo}': '{bruto}'."
        ) from exc


def exigir_colunas(
    linhas: list[dict[str, str]], obrigatorias: set[str], arquivo: str
) -> None:
    if not linhas:
        return
    faltantes = obrigatorias - set(linhas[0].keys())
    if faltantes:
        raise ErroDeDadosError(
            f"A base '{arquivo}' está sem as colunas: {', '.join(sorted(faltantes))}."
        )
