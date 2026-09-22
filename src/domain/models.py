"""Modelos de domínio — representações tipadas das entidades do banco."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class Cliente:
    cpf: str
    nome: str
    data_nascimento: date
    limite_atual: float
    score: int

    @property
    def primeiro_nome(self) -> str:
        return self.nome.split()[0]


@dataclass(frozen=True, slots=True)
class FaixaScore:
    """Uma linha de score_limite.csv: até quanto de limite um score permite."""

    score_min: int
    score_max: int
    limite_maximo: float

    def contem(self, score: int) -> bool:
        return self.score_min <= score <= self.score_max


@dataclass(frozen=True, slots=True)
class SolicitacaoAumento:
    cpf_cliente: str
    data_hora_solicitacao: str  # ISO 8601
    limite_atual: float
    novo_limite_solicitado: float
    status_pedido: str  # 'pendente' | 'aprovado' | 'rejeitado'


@dataclass(frozen=True, slots=True)
class RespostaEntrevista:
    renda_mensal: float
    tipo_emprego: str  # 'formal' | 'autonomo' | 'desempregado'
    despesas_fixas: float
    num_dependentes: int
    tem_dividas: bool
