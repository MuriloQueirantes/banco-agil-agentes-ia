"""Interface de atendimento do Banco Ágil (Streamlit).

    streamlit run app.py

A tela tem dois lados deliberadamente distintos:

* o **atendimento**, que é o que um cliente veria — uma conversa contínua com
  a Ági, sem qualquer sinal de que existem quatro agentes por trás;
* os **bastidores**, na barra lateral, que expõem para quem avalia o sistema o
  percurso interno de cada turno: agente, ferramenta, estado da sessão.
"""

from __future__ import annotations

import html

import streamlit as st

from src.atendimento import SessaoAtendimento
from src.config import LLM_MODEL, SOLICITACOES_CSV
from src.domain.exceptions import ErroDeDadosError
from src.domain.validators import formatar_cpf
from src.llm import ConfiguracaoAusenteError, criar_llm
from src.repositories.clientes import listar_clientes
from src.ui import rotulos
from src.ui.estilos import FOLHA_DE_ESTILO

st.set_page_config(
    page_title="Banco Ágil · Atendimento",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(FOLHA_DE_ESTILO, unsafe_allow_html=True)


# ---------------------------------------------------------------- sessão --
def nova_sessao() -> None:
    st.session_state.sessao = SessaoAtendimento()
    st.session_state.conversa = []
    st.session_state.abertura_pendente = True


if "sessao" not in st.session_state:
    nova_sessao()

sessao: SessaoAtendimento = st.session_state.sessao


def registrar(autor: str, texto: str) -> None:
    st.session_state.conversa.append({"autor": autor, "texto": texto})


# ----------------------------------------------------------- bastidores --
def desenhar_bastidores() -> None:
    dados = sessao.bastidores()

    st.markdown('<div class="bast__titulo">sessão</div>', unsafe_allow_html=True)

    autenticado = (
        '<span class="campo__valor campo__valor--sim">sim</span>'
        if dados.autenticado
        else '<span class="campo__valor campo__valor--nao">não</span>'
    )
    campos = [
        ("agente ativo", f'<span class="campo__valor">{rotulos.agente(dados.agente_atual)}</span>'),
        ("especialidade", f'<span class="campo__valor">{html.escape(dados.especialidade)}</span>'),
        ("autenticado", autenticado),
    ]
    if dados.cliente:
        campos.append(("cliente", f'<span class="campo__valor">{html.escape(dados.cliente)}</span>'))
        campos.append(("cpf", f'<span class="campo__valor">{dados.cpf_mascarado}</span>'))
    else:
        cor = "--alerta" if dados.tentativas_autenticacao >= 2 else "--nao"
        campos.append((
            "tentativas",
            f'<span class="campo__valor campo__valor{cor}">'
            f"{dados.tentativas_autenticacao} de 3</span>",
        ))
    if dados.status_ultima_solicitacao:
        cor = "--sim" if dados.status_ultima_solicitacao == "aprovado" else "--alerta"
        campos.append((
            "último pedido",
            f'<span class="campo__valor campo__valor{cor}">'
            f"{rotulos.STATUS.get(dados.status_ultima_solicitacao, '—')}</span>",
        ))
    if dados.entrevista_concluida:
        campos.append(("entrevista", '<span class="campo__valor campo__valor--sim">concluída</span>'))
    if dados.encerrado:
        campos.append(("atendimento", '<span class="campo__valor campo__valor--alerta">encerrado</span>'))

    st.markdown(
        "".join(
            f'<div class="campo"><span class="campo__rotulo">{rotulo}</span>{valor}</div>'
            for rotulo, valor in campos
        ),
        unsafe_allow_html=True,
    )

    # -- trilha do último turno --
    st.markdown(
        '<div class="bast__titulo">trilha do último turno</div>',
        unsafe_allow_html=True,
    )
    if not dados.trilha_do_turno:
        st.markdown(
            '<p class="vazio">Envie uma mensagem para ver o percurso.</p>',
            unsafe_allow_html=True,
        )
    else:
        passos = []
        for evento in dados.trilha_do_turno:
            if evento.tipo == "agente":
                passos.append(
                    f'<div class="passo passo--agente">{rotulos.agente(evento.nome)}</div>'
                )
            else:
                passos.append(
                    '<div class="passo passo--ferramenta">'
                    f"<strong>{html.escape(rotulos.ferramenta(evento.nome))}</strong></div>"
                )
        st.markdown(f'<div class="trilha">{"".join(passos)}</div>', unsafe_allow_html=True)

    # -- clientes para teste --
    st.markdown(
        '<div class="bast__titulo">clientes de teste</div>', unsafe_allow_html=True
    )
    try:
        fichas = []
        for cliente in listar_clientes():
            fichas.append(
                '<div class="ficha">'
                f'<div class="ficha__nome">{html.escape(cliente.nome)}</div>'
                f'<div class="ficha__dados">{formatar_cpf(cliente.cpf)} · '
                f'{cliente.data_nascimento.strftime("%d/%m/%Y")}</div>'
                f'<div class="ficha__marca">score {cliente.score} · '
                f'limite R$ {cliente.limite_atual:,.0f}'.replace(",", ".")
                + "</div></div>"
            )
        st.markdown("".join(fichas), unsafe_allow_html=True)
    except ErroDeDadosError as erro:
        st.markdown(f'<p class="vazio">{html.escape(str(erro))}</p>', unsafe_allow_html=True)

    # -- pedidos já gravados no CSV para este cliente --
    pedidos = sessao.pedidos_do_cliente()
    if pedidos:
        st.markdown(
            f'<div class="bast__titulo">{SOLICITACOES_CSV.name}</div>',
            unsafe_allow_html=True,
        )
        linhas = "".join(
            '<div class="campo">'
            f'<span class="campo__rotulo">R$ {p.novo_limite_solicitado:,.0f}</span>'.replace(",", ".")
            + f'<span class="campo__valor campo__valor--'
            f'{"sim" if p.status_pedido == "aprovado" else "alerta"}">'
            f"{p.status_pedido}</span></div>"
            for p in pedidos[-6:]
        )
        st.markdown(linhas, unsafe_allow_html=True)

    st.markdown('<div class="bast__titulo">controles</div>', unsafe_allow_html=True)
    if st.button("Novo atendimento"):
        nova_sessao()
        st.rerun()
    st.markdown(
        f'<div class="campo"><span class="campo__rotulo">modelo</span>'
        f'<span class="campo__valor">{LLM_MODEL}</span></div>',
        unsafe_allow_html=True,
    )


with st.sidebar:
    desenhar_bastidores()


# -------------------------------------------------------------- cabeçalho --
ponto = "" if not sessao.encerrado else " marca__ponto--off"
st.markdown(
    '<div class="marca">'
    '<span class="marca__nome">Banco <em>Á</em>gil</span>'
    '<span class="marca__papel">atendimento</span>'
    f'<span class="marca__ponto{ponto}"></span>'
    "</div>",
    unsafe_allow_html=True,
)


# ------------------------------------------------------- pré-requisitos --
try:
    criar_llm()
except ConfiguracaoAusenteError as erro:
    st.markdown(
        '<div class="convite"><h2>Falta a chave da API</h2>'
        f"<p>{html.escape(str(erro))}</p></div>",
        unsafe_allow_html=True,
    )
    st.stop()


# ------------------------------------------------------------- abertura --
if st.session_state.abertura_pendente:
    with st.spinner(""):
        registrar("agente", sessao.iniciar())
    st.session_state.abertura_pendente = False


# -------------------------------------------------------------- conversa --
for turno in st.session_state.conversa:
    if turno["autor"] == "sistema":
        st.markdown(
            f'<div class="turno"><div class="balao balao--sistema">'
            f'{html.escape(turno["texto"])}</div></div>',
            unsafe_allow_html=True,
        )
        continue

    de_agente = turno["autor"] == "agente"
    if de_agente:
        st.markdown('<p class="assinatura">Ági</p>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="turno turno--{"agente" if de_agente else "cliente"}">'
        f'<div class="balao balao--{"agente" if de_agente else "cliente"}">'
        f'{html.escape(turno["texto"])}</div></div>',
        unsafe_allow_html=True,
    )

if sessao.encerrado:
    st.markdown(
        '<div class="turno"><div class="balao balao--sistema">'
        "atendimento encerrado · use “novo atendimento” para recomeçar"
        "</div></div>",
        unsafe_allow_html=True,
    )


# ----------------------------------------------------------------- campo --
mensagem = st.chat_input(
    "Escreva sua mensagem…" if not sessao.encerrado else "Atendimento encerrado",
    disabled=sessao.encerrado,
)

if mensagem:
    registrar("cliente", mensagem)
    with st.spinner(""):
        resposta = sessao.enviar(mensagem)
    registrar("agente", resposta)
    st.rerun()
