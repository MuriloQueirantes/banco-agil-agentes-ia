"""Exceções de domínio.

Separar erros *esperados* (ErroDeNegocio) de erros *inesperados* permite que a
camada de tools traduza os primeiros em mensagens úteis ao cliente e trate os
segundos como falha técnica genérica, sempre sem derrubar a conversa.
"""

from __future__ import annotations


class BancoAgilError(Exception):
    """Raiz de todos os erros da aplicação."""


class ErroDeNegocio(BancoAgilError):
    """Erro previsto, cuja mensagem pode ser exibida ao cliente."""


class EntradaInvalidaError(ErroDeNegocio):
    """O dado informado pelo cliente não passou na validação."""


class ClienteNaoEncontradoError(ErroDeNegocio):
    """Nenhum cliente corresponde aos dados informados."""


class ErroDeDadosError(BancoAgilError):
    """Falha ao ler ou escrever uma das bases CSV."""


class ErroDeIntegracaoError(BancoAgilError):
    """Falha ao consultar um serviço externo (ex.: API de câmbio)."""
