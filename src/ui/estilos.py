"""Folha de estilo da interface.

Direção visual: **palco e bastidores**.

O enunciado exige que o cliente não perceba a troca entre agentes — mas quem
avalia o sistema precisa enxergá-la. A interface resolve essa tensão com duas
linguagens visuais que nunca se misturam:

* **Palco** (área da conversa): tipografia humana, balões arredondados, âmbar
  como a voz da Ági. É o que o cliente veria.
* **Bastidores** (barra lateral): monoespaçada, ciano, régua de telemetria.
  É a máquina aparecendo — o percurso do turno pelos agentes e ferramentas.

O âmbar nunca aparece nos bastidores e o ciano nunca aparece no palco: a cor
é que separa o que é atendimento do que é diagnóstico.
"""

FOLHA_DE_ESTILO = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,800&family=Public+Sans:ital,wght@0,400;0,500;0,600;1,400&family=JetBrains+Mono:wght@400;500;700&display=swap');

:root {
  --tinta:        #0B1017;
  --superficie:   #131B25;
  --superficie-2: #1A2531;
  --linha:        #22303F;
  --texto:        #E4E9EF;
  --texto-fraco:  #8493A5;
  --ambar:        #E8A33D;
  --ambar-fosco:  #3A2C14;
  --ciano:        #5AD5C4;
  --ciano-fosco:  #123029;
  --alerta:       #E0736C;

  --display: 'Bricolage Grotesque', 'Public Sans', system-ui, sans-serif;
  --corpo:   'Public Sans', system-ui, -apple-system, sans-serif;
  --mono:    'JetBrains Mono', ui-monospace, 'SF Mono', monospace;
}

/* ---------------------------------------------------------------- base -- */
.stApp { background: var(--tinta); }

html, body, [class*="st-"], .stMarkdown, p, div, span, li {
  font-family: var(--corpo);
}

[data-testid="stMainBlockContainer"] {
  max-width: 47rem;
  padding-top: 2.2rem;
  padding-bottom: 7rem;
}

#MainMenu, footer, [data-testid="stHeader"] { visibility: hidden; height: 0; }

/* -------------------------------------------------------------- marca -- */
.marca {
  display: flex;
  align-items: baseline;
  gap: .6rem;
  padding-bottom: .7rem;
  border-bottom: 1px solid var(--linha);
  margin-bottom: 1.8rem;
}
.marca__nome {
  font-family: var(--display);
  font-weight: 800;
  font-size: 1.32rem;
  letter-spacing: -.028em;
  color: var(--texto);
}
/* O acento agudo do "Ágil" é a marca: o único glifo em âmbar do cabeçalho. */
.marca__nome em { font-style: normal; color: var(--ambar); }
.marca__papel {
  font-family: var(--mono);
  font-size: .66rem;
  letter-spacing: .13em;
  text-transform: uppercase;
  color: var(--texto-fraco);
}
.marca__ponto {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--ambar);
  margin-left: auto;
  align-self: center;
  box-shadow: 0 0 0 4px var(--ambar-fosco);
}
.marca__ponto--off { background: var(--texto-fraco); box-shadow: none; }

/* -------------------------------------------------------------- balões -- */
.turno { display: flex; margin-bottom: .95rem; }
.turno--agente  { justify-content: flex-start; }
.turno--cliente { justify-content: flex-end; }

.balao {
  max-width: 82%;
  padding: .72rem .95rem;
  font-size: .945rem;
  line-height: 1.58;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.balao--agente {
  background: var(--superficie);
  border: 1px solid var(--linha);
  border-left: 2px solid var(--ambar);
  border-radius: 3px 13px 13px 13px;
  color: var(--texto);
}
.balao--cliente {
  background: var(--superficie-2);
  border: 1px solid var(--linha);
  border-radius: 13px 3px 13px 13px;
  color: var(--texto);
}
.balao--sistema {
  max-width: 100%;
  text-align: center;
  font-family: var(--mono);
  font-size: .7rem;
  letter-spacing: .1em;
  text-transform: uppercase;
  color: var(--texto-fraco);
  border-top: 1px solid var(--linha);
  padding-top: .9rem;
  margin-top: .4rem;
}

.assinatura {
  font-family: var(--mono);
  font-size: .62rem;
  letter-spacing: .12em;
  text-transform: uppercase;
  color: var(--texto-fraco);
  margin: 0 0 .28rem .1rem;
}

/* --------------------------------------------------------- estado vazio -- */
.convite {
  border: 1px dashed var(--linha);
  border-radius: 6px;
  padding: 2.4rem 1.6rem;
  text-align: center;
}
.convite h2 {
  font-family: var(--display);
  font-weight: 600;
  font-size: 1.15rem;
  letter-spacing: -.02em;
  color: var(--texto);
  margin: 0 0 .45rem;
}
.convite p { color: var(--texto-fraco); font-size: .88rem; margin: 0; }

/* ------------------------------------------------------------ campo de -- */
[data-testid="stChatInput"] {
  background: var(--superficie);
  border: 1px solid var(--linha);
  border-radius: 8px;
}
[data-testid="stChatInput"] textarea { font-family: var(--corpo); }
[data-testid="stBottomBlockContainer"] { background: var(--tinta); }

/* ---------------------------------------------------------- bastidores -- */
[data-testid="stSidebar"] {
  background: #080C12;
  border-right: 1px solid var(--linha);
}
[data-testid="stSidebar"] * { font-family: var(--mono); }

.bast__titulo {
  font-size: .63rem;
  letter-spacing: .18em;
  text-transform: uppercase;
  color: var(--ciano);
  padding-bottom: .4rem;
  border-bottom: 1px solid var(--linha);
  margin: 1.5rem 0 .75rem;
}
.bast__titulo:first-of-type { margin-top: .2rem; }

.campo {
  display: flex;
  justify-content: space-between;
  gap: .7rem;
  font-size: .715rem;
  padding: .21rem 0;
}
.campo__rotulo { color: var(--texto-fraco); }
.campo__valor  { color: var(--texto); text-align: right; overflow-wrap: anywhere; }
.campo__valor--sim  { color: var(--ciano); }
.campo__valor--nao  { color: var(--texto-fraco); }
.campo__valor--alerta { color: var(--alerta); }

/* Trilha: régua vertical com um nó por passo do turno. */
.trilha { position: relative; padding-left: 1.05rem; margin-top: .2rem; }
.trilha::before {
  content: '';
  position: absolute;
  left: 3px; top: .45rem; bottom: .45rem;
  width: 1px;
  background: var(--linha);
}
.passo { position: relative; font-size: .7rem; padding: .23rem 0; }
.passo::before {
  content: '';
  position: absolute;
  left: -1.05rem; top: .55rem;
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--tinta);
  border: 1px solid var(--linha);
}
.passo--agente {
  color: var(--ciano);
  text-transform: uppercase;
  letter-spacing: .1em;
  font-weight: 700;
  font-size: .655rem;
  padding-top: .5rem;
}
.passo--agente::before { background: var(--ciano); border-color: var(--ciano); }
.passo--agente:first-child { padding-top: .23rem; }
.passo--ferramenta { color: var(--texto-fraco); }
.passo--ferramenta strong { color: var(--texto); font-weight: 500; }

.vazio { font-size: .7rem; color: var(--texto-fraco); font-style: italic; }

.ficha {
  border: 1px solid var(--linha);
  border-left: 2px solid var(--ciano);
  border-radius: 3px;
  padding: .45rem .6rem;
  margin-bottom: .4rem;
  font-size: .685rem;
  line-height: 1.55;
}
.ficha__nome { color: var(--texto); }
.ficha__dados { color: var(--texto-fraco); }
.ficha__marca { color: var(--ciano); }

[data-testid="stSidebar"] .stButton button {
  width: 100%;
  background: transparent;
  border: 1px solid var(--linha);
  color: var(--texto-fraco);
  border-radius: 3px;
  font-size: .68rem;
  letter-spacing: .1em;
  text-transform: uppercase;
  padding: .45rem;
}
[data-testid="stSidebar"] .stButton button:hover {
  border-color: var(--ciano);
  color: var(--ciano);
}

/* ------------------------------------------------------------ conforto -- */
*:focus-visible { outline: 2px solid var(--ambar); outline-offset: 2px; }

@media (prefers-reduced-motion: no-preference) {
  .turno { animation: surge .22s ease-out; }
  @keyframes surge {
    from { opacity: 0; transform: translateY(5px); }
    to   { opacity: 1; transform: none; }
  }
}

@media (max-width: 640px) {
  .balao { max-width: 92%; }
  [data-testid="stMainBlockContainer"] { padding-top: 1.2rem; }
}
</style>
"""
