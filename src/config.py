"""Configuração central: caminhos, parâmetros de negócio e do LLM.

Tudo que é "ajustável" do sistema vive aqui, para que regras de negócio
(pesos do score, nº de tentativas de autenticação) não fiquem espalhadas
pelo código nem escondidas dentro dos prompts.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --------------------------------------------------------------------------
# Caminhos
# --------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("BANCO_AGIL_DATA_DIR", BASE_DIR / "data"))

CLIENTES_CSV = DATA_DIR / "clientes.csv"
SCORE_LIMITE_CSV = DATA_DIR / "score_limite.csv"
SOLICITACOES_CSV = DATA_DIR / "solicitacoes_aumento_limite.csv"

LOG_DIR = Path(os.getenv("BANCO_AGIL_LOG_DIR", BASE_DIR / "logs"))
LOG_FILE = LOG_DIR / "banco_agil.log"

# --------------------------------------------------------------------------
# LLM
# --------------------------------------------------------------------------
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# Alias, e não uma versão fixa, de propósito: o Google descontinua modelos com
# alguma frequência (este projeto começou em gemini-2.0-flash, que saiu do ar
# durante o desenvolvimento) e um repositório clonado meses depois deve
# continuar funcionando. Para fixar uma versão exata e ter reprodutibilidade
# total, defina BANCO_AGIL_MODEL no .env.
LLM_MODEL = os.getenv("BANCO_AGIL_MODEL", "gemini-flash-latest")
LLM_TEMPERATURE = float(os.getenv("BANCO_AGIL_TEMPERATURE", "0.2"))

# --------------------------------------------------------------------------
# Regras de negócio — autenticação
# --------------------------------------------------------------------------
MAX_TENTATIVAS_AUTENTICACAO = 3

# --------------------------------------------------------------------------
# Regras de negócio — fórmula de score (0 a 1000)
# --------------------------------------------------------------------------
SCORE_MINIMO = 0
SCORE_MAXIMO = 1000

PESO_RENDA = 30

PESO_EMPREGO: dict[str, int] = {
    "formal": 300,
    "autonomo": 200,
    "desempregado": 0,
}

PESO_DEPENDENTES: dict[str, int] = {
    "0": 100,
    "1": 80,
    "2": 60,
    "3+": 30,
}

PESO_DIVIDAS: dict[str, int] = {
    "sim": -100,
    "nao": 100,
}

# Teto aplicado ao componente de renda antes da soma, para que uma renda
# declarada absurdamente alta não estoure sozinha a escala de 1000 pontos.
TETO_COMPONENTE_RENDA = 600

# --------------------------------------------------------------------------
# Câmbio
# --------------------------------------------------------------------------
COTACAO_API_PRIMARIA = "https://economia.awesomeapi.com.br/json/last/{par}"
COTACAO_API_FALLBACK = "https://open.er-api.com/v6/latest/{base}"
COTACAO_TIMEOUT_SEGUNDOS = 8

MOEDAS_SUPORTADAS: dict[str, str] = {
    "USD": "Dólar americano",
    "EUR": "Euro",
    "GBP": "Libra esterlina",
    "ARS": "Peso argentino",
    "JPY": "Iene japonês",
    "CAD": "Dólar canadense",
    "AUD": "Dólar australiano",
    "CHF": "Franco suíço",
    "BTC": "Bitcoin",
    "ETH": "Ethereum",
}
