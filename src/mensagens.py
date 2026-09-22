"""Extração do texto exibível de uma mensagem do LLM.

A partir do langchain-core 1.x, `AIMessage.content` nem sempre é uma string:
modelos que devolvem blocos tipados (texto, raciocínio, assinaturas internas)
entregam uma **lista de dicionários**. Exibir isso direto na interface mostra
JSON ao cliente — foi exatamente o que aconteceu na primeira execução contra o
Gemini.

Esta função normaliza os dois formatos num único `str`, ignorando blocos que
não sejam texto (assinaturas e metadados do provedor não são para ler).
"""

from __future__ import annotations

from typing import Any


def texto_de(mensagem: Any) -> str:
    """Texto legível de uma mensagem, seja `content` string ou lista de blocos."""
    conteudo = getattr(mensagem, "content", mensagem)

    if isinstance(conteudo, str):
        return conteudo.strip()

    if isinstance(conteudo, list):
        partes: list[str] = []
        for bloco in conteudo:
            if isinstance(bloco, str):
                partes.append(bloco)
            elif isinstance(bloco, dict) and bloco.get("type") == "text":
                partes.append(str(bloco.get("text", "")))
        return "".join(partes).strip()

    return str(conteudo).strip() if conteudo else ""
