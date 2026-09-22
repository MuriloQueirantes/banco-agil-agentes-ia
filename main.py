"""Atendimento do Banco Ágil no terminal.

    python main.py

Uma alternativa à interface Streamlit, útil para depurar o fluxo rapidamente.
Use `--bastidores` para ver, a cada turno, o percurso interno entre agentes e
ferramentas.
"""

from __future__ import annotations

import argparse
import sys

from src.atendimento import SessaoAtendimento
from src.llm import ConfiguracaoAusenteError, criar_llm
from src.ui import rotulos

AMBAR = "\033[38;5;215m"
CIANO = "\033[38;5;80m"
FRACO = "\033[38;5;245m"
FIM = "\033[0m"

ENCERRAR = {"sair", "exit", "quit", ":q"}


def imprimir_agente(texto: str) -> None:
    print(f"\n{AMBAR}Ági{FIM}  {texto}\n")


def imprimir_trilha(sessao: SessaoAtendimento) -> None:
    trilha = sessao.bastidores().trilha_do_turno
    if not trilha:
        return
    partes = [
        (
            f"{CIANO}[{rotulos.agente(e.nome)}]{FIM}"
            if e.tipo == "agente"
            else f"{FRACO}{rotulos.ferramenta(e.nome)}{FIM}"
        )
        for e in trilha
    ]
    print(f"  {FRACO}·{FIM} " + f" {FRACO}→{FIM} ".join(partes))


def main() -> int:
    analisador = argparse.ArgumentParser(description="Banco Ágil — atendimento no terminal")
    analisador.add_argument(
        "--bastidores",
        action="store_true",
        help="mostra o percurso interno entre agentes e ferramentas a cada turno",
    )
    argumentos = analisador.parse_args()

    try:
        criar_llm()
    except ConfiguracaoAusenteError as erro:
        print(f"\n{erro}\n", file=sys.stderr)
        return 1

    print(f"\n{AMBAR}Banco Ágil{FIM} {FRACO}· atendimento (digite 'sair' para encerrar){FIM}")

    sessao = SessaoAtendimento()
    imprimir_agente(sessao.iniciar())
    if argumentos.bastidores:
        imprimir_trilha(sessao)

    while not sessao.encerrado:
        try:
            entrada = input("você  ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\nAtendimento interrompido. Até logo!\n")
            return 0

        if not entrada:
            continue
        if entrada.lower() in ENCERRAR:
            print("\nAtendimento interrompido. Até logo!\n")
            return 0

        imprimir_agente(sessao.enviar(entrada))
        if argumentos.bastidores:
            imprimir_trilha(sessao)

    print(f"{FRACO}— atendimento encerrado —{FIM}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
