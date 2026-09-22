"""Validação e normalização das entradas do cliente.

Esta camada é deliberadamente independente do LLM: o modelo extrai o valor
bruto da fala do cliente e passa para cá, onde a validação é determinística.
Assim o agente nunca "acredita" num CPF inválido só porque parecia certo.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

from src.domain.exceptions import EntradaInvalidaError

_SO_DIGITOS = re.compile(r"\D")

FORMATOS_DATA = (
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%y",
)


def normalizar_texto(valor: str) -> str:
    """Minúsculas, sem acentos e sem espaços nas pontas."""
    sem_acento = unicodedata.normalize("NFKD", valor or "")
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return sem_acento.strip().lower()


# --------------------------------------------------------------------------
# CPF
# --------------------------------------------------------------------------
def somente_digitos(valor: str) -> str:
    return _SO_DIGITOS.sub("", valor or "")


def _digitos_verificadores(base: str) -> str:
    digitos = ""
    for peso_inicial in (10, 11):
        soma = sum(
            int(n) * p for n, p in zip(base + digitos, range(peso_inicial, 1, -1))
        )
        resto = (soma * 10) % 11
        digitos += str(0 if resto == 10 else resto)
    return digitos


def cpf_e_valido(cpf: str) -> bool:
    """Valida os dígitos verificadores do CPF (algoritmo da Receita Federal)."""
    numeros = somente_digitos(cpf)
    if len(numeros) != 11 or numeros == numeros[0] * 11:
        return False
    return numeros[9:] == _digitos_verificadores(numeros[:9])


def normalizar_cpf(cpf: str) -> str:
    """Devolve o CPF com 11 dígitos, ou levanta EntradaInvalidaError."""
    numeros = somente_digitos(cpf)
    if len(numeros) != 11:
        raise EntradaInvalidaError(
            "O CPF precisa ter 11 dígitos. "
            f"Recebi {len(numeros)} dígito(s) em '{cpf}'."
        )
    if not cpf_e_valido(numeros):
        raise EntradaInvalidaError(
            "Esse CPF não é válido — os dígitos verificadores não conferem."
        )
    return numeros


def formatar_cpf(cpf: str) -> str:
    n = somente_digitos(cpf)
    return f"{n[:3]}.{n[3:6]}.{n[6:9]}-{n[9:]}" if len(n) == 11 else cpf


def mascarar_cpf(cpf: str) -> str:
    """Exibição segura em logs e UI: 123.***.**9-00 -> ***.***.*89-01."""
    n = somente_digitos(cpf)
    return f"***.***.{n[6:9]}-{n[9:]}" if len(n) == 11 else "***"


# --------------------------------------------------------------------------
# Data de nascimento
# --------------------------------------------------------------------------
def normalizar_data(valor: str) -> date:
    """Aceita os formatos usuais em português e devolve um `date`."""
    bruto = (valor or "").strip()
    if not bruto:
        raise EntradaInvalidaError("A data de nascimento não foi informada.")

    for formato in FORMATOS_DATA:
        try:
            parsed = datetime.strptime(bruto, formato).date()
        except ValueError:
            continue
        if parsed > date.today():
            raise EntradaInvalidaError(
                "A data de nascimento informada está no futuro."
            )
        return parsed

    raise EntradaInvalidaError(
        f"Não consegui interpretar a data '{bruto}'. "
        "Use o formato DD/MM/AAAA, por exemplo 14/03/1988."
    )


# --------------------------------------------------------------------------
# Valores monetários
# --------------------------------------------------------------------------
def normalizar_valor_monetario(valor: str | float | int) -> float:
    """Aceita 'R$ 5.000,00', '5000.50', 5000 e devolve float >= 0."""
    if isinstance(valor, (int, float)):
        numero = float(valor)
    else:
        texto = (valor or "").strip()
        texto = re.sub(r"[R$\s]", "", texto, flags=re.IGNORECASE)
        if "," in texto and "." in texto:
            # 5.000,00 -> 5000.00   |   5,000.00 -> 5000.00
            texto = (
                texto.replace(".", "").replace(",", ".")
                if texto.rfind(",") > texto.rfind(".")
                else texto.replace(",", "")
            )
        elif "," in texto:
            texto = texto.replace(",", ".")
        try:
            numero = float(texto)
        except ValueError as exc:
            raise EntradaInvalidaError(
                f"Não consegui interpretar o valor '{valor}'."
            ) from exc

    if numero < 0:
        raise EntradaInvalidaError("O valor não pode ser negativo.")
    if numero != numero or numero in (float("inf"), float("-inf")):
        raise EntradaInvalidaError("O valor informado não é um número válido.")
    return round(numero, 2)


# --------------------------------------------------------------------------
# Campos categóricos da entrevista
# --------------------------------------------------------------------------
_EMPREGO_SINONIMOS = {
    "formal": "formal",
    "clt": "formal",
    "carteira assinada": "formal",
    "assalariado": "formal",
    "servidor publico": "formal",
    "autonomo": "autonomo",
    "auto-nomo": "autonomo",
    "freelancer": "autonomo",
    "freela": "autonomo",
    "pj": "autonomo",
    "mei": "autonomo",
    "empresario": "autonomo",
    "informal": "autonomo",
    "desempregado": "desempregado",
    "desempregada": "desempregado",
    "sem emprego": "desempregado",
    "nenhum": "desempregado",
    "aposentado": "formal",
}


def normalizar_tipo_emprego(valor: str) -> str:
    chave = normalizar_texto(valor)
    if chave in _EMPREGO_SINONIMOS:
        return _EMPREGO_SINONIMOS[chave]
    for sinonimo, canonico in _EMPREGO_SINONIMOS.items():
        if sinonimo in chave:
            return canonico
    raise EntradaInvalidaError(
        f"Não reconheci o tipo de emprego '{valor}'. "
        "As opções são: formal, autônomo ou desempregado."
    )


def normalizar_booleano(valor: str | bool) -> bool:
    if isinstance(valor, bool):
        return valor
    chave = normalizar_texto(str(valor))
    if chave in {"sim", "s", "true", "1", "tenho", "possuo", "yes", "y"}:
        return True
    if chave in {"nao", "n", "false", "0", "nenhuma", "nenhum", "no"}:
        return False
    raise EntradaInvalidaError(
        f"Não entendi a resposta '{valor}'. Responda com 'sim' ou 'não'."
    )


def normalizar_dependentes(valor: str | int) -> int:
    if isinstance(valor, bool):
        raise EntradaInvalidaError("Número de dependentes inválido.")
    if isinstance(valor, int):
        numero = valor
    else:
        digitos = somente_digitos(str(valor))
        chave = normalizar_texto(str(valor))
        if not digitos:
            por_extenso = {
                "nenhum": 0, "nenhuma": 0, "zero": 0, "um": 1, "uma": 1,
                "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5,
            }
            if chave in por_extenso:
                numero = por_extenso[chave]
            else:
                raise EntradaInvalidaError(
                    f"Não consegui interpretar '{valor}' como número de dependentes."
                )
        else:
            numero = int(digitos)

    if numero < 0:
        raise EntradaInvalidaError("O número de dependentes não pode ser negativo.")
    if numero > 30:
        raise EntradaInvalidaError(
            "O número de dependentes informado parece fora do esperado."
        )
    return numero
