"""Tradução de nomes internos para linguagem de interface.

O painel de bastidores mostra o que o sistema fez, não como as funções se
chamam no código. Um avaliador lendo "registrou o pedido de aumento" entende
na hora; "solicitar_aumento_limite" ele precisa decifrar.
"""

from __future__ import annotations

AGENTES: dict[str, str] = {
    "triagem": "Triagem",
    "credito": "Crédito",
    "entrevista": "Entrevista",
    "cambio": "Câmbio",
}

FERRAMENTAS: dict[str, str] = {
    "autenticar_cliente": "conferiu CPF e data de nascimento",
    "consultar_limite_credito": "consultou o limite disponível",
    "solicitar_aumento_limite": "registrou o pedido de aumento",
    "consultar_historico_solicitacoes": "leu o histórico de pedidos",
    "calcular_e_salvar_novo_score": "recalculou e gravou o score",
    "consultar_cotacao_moeda": "buscou a cotação na API externa",
    "transferir_para_credito": "encaminhou para crédito",
    "transferir_para_cambio": "encaminhou para câmbio",
    "transferir_para_entrevista": "encaminhou para a entrevista",
    "transferir_para_triagem": "voltou para a triagem",
    "encerrar_atendimento": "encerrou o atendimento",
}

STATUS: dict[str, str] = {
    "pendente": "pendente",
    "aprovado": "aprovado",
    "rejeitado": "rejeitado",
}


def agente(nome: str) -> str:
    return AGENTES.get(nome, nome.capitalize())


def ferramenta(nome: str) -> str:
    return FERRAMENTAS.get(nome, nome.replace("_", " "))
