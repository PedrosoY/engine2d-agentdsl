# Engine 2D + AgentDSL

Projeto único para duas disciplinas (Engenharia de Computação — FHO):

| Disciplina | Parte do projeto | Onde está |
|---|---|---|
| **Computação Gráfica** | Mini engine 2D em Python + OpenGL 3.3: sprites, texturas PNG com alfa, transformações T·R·S, camadas, câmera, renderização individual x em lote (instancing) x atlas | `engine2d/`, `demo_engine.py`, `benchmark_engine.py` |
| **Teoria da Computação e Compiladores** | AgentDSL: linguagem orientada a eventos (inspirada em AgentSpeak/Jason) com lexer, parser descendente recursivo, análise semântica e interpretador, cujas ações controlam os sprites da engine | `agentdsl/`, `GRAMATICA.md`, `exemplos/`, `jogo.py`, `benchmark_dsl.py` |

A engine não sabe nada sobre agentes; a DSL não sabe nada sobre OpenGL. Elas se
encontram só em `agentdsl/ponte_engine.py` (ações → sprite, sprite → percepções).

```
 exemplos/jogo.agt ──► Lexer ──► Parser ──► AST ──► Semântica ──► Interpretador
                                                                     │  ▲
                                                     ações (mover…)  ▼  │ percepções (+jogador_perto…)
                                                               ponte_engine.py
                                                                     │
 engine2d:  Cena ─► ordenação por camada ─► Renderizador ─► vertex shader ─► rasterização ─► fragment shader
```

## Instalação

Python 3.10+ e uma GPU/driver com OpenGL 3.3.

```powershell
pip install -r requirements.txt
```

## Como rodar

```powershell
python demo_engine.py
```
Demo da engine. WASD/setas movem a câmera, roda do mouse dá zoom, clique e arraste
seleciona/move sprites, Q/E giram, Z/X mudam a escala, PgUp/PgDn mudam a camada,
+/- adicionam/removem 200 sprites, **M** alterna renderização individual/lote.

```powershell
python jogo.py
```
Cenário experimental da DSL ("Pega-Fujão"). Todos os personagens, exceto o
jogador (azul), são agentes de `exemplos/jogo.agt`. WASD move, ESPAÇO ataca,
**TAB** mostra as crenças e o log de eventos de cada agente na tela, **R** recarrega
o `.agt` (edite o arquivo com o jogo aberto e aperte R).

```powershell
python -m agentdsl verificar exemplos/jogo.agt
```
Outros comandos da CLI: `tokens`, `ast`, `simbolos`, `executar` (sem gráficos), `jogo`.
Exemplos com erros de propósito em `exemplos/invalidos/`.

```powershell
python -m pytest
```
Testes (use `-m "not gpu"` numa máquina sem OpenGL).

```powershell
python benchmark_engine.py
```
```powershell
python benchmark_dsl.py
```
Geram os CSVs e gráficos de `resultados/` usados nos artigos.

---

## Parte 1 — Engine 2D (Computação Gráfica)

| Módulo | Responsabilidade |
|---|---|
| `matematica.py` | Matrizes 3×3 homogêneas: T, R, S, M = T·R·S (forma fechada e vetorizada), ortográfica |
| `transformacao.py` | Tx, Ty, θ, Sx, Sy com cache da matriz (só recalcula quando muda) |
| `sprite.py` | S = {Tx, Ty, θ, Sx, Sy, L, I} + tamanho, cor, região UV, seleção por mouse |
| `cena.py` | Instâncias e ordenação estável por camada (só reordena quando algo muda) |
| `camera.py` | Pan, zoom, rotação; conversão tela → mundo |
| `textura.py` | PNG → textura RGBA (com flip vertical), cache, atlas por prateleiras |
| `shader.py` | GLSL 330 core: shader individual e instanciado |
| `renderizador.py` | Modo `individual` (1 draw call por sprite) e modo `lote` (instancing) |
| `motor.py` | Janela/contexto (pygame), loop principal, HUD de texto, captura de tela |

Três estratégias de desenho são comparadas no benchmark:

- **individual** — o pipeline do artigo: para cada sprite, envia a matriz de modelo como
  uniform e chama `glDrawArrays`.
- **lote** — os sprites ordenados são agrupados em sequências consecutivas de mesma textura;
  cada sequência vira um `glDrawArraysInstanced`, com as matrizes calculadas de uma vez no
  numpy. A ordem das camadas é preservada.
- **lote_agrupado** — além disso, ordena por textura *dentro* da mesma camada (troca a ordem
  de inserção dentro da camada por menos quebras de lote).
- **lote_atlas** — todas as imagens num único atlas: a cena inteira sai em 1 draw call, com a
  ordem exata das camadas.

## Parte 2 — AgentDSL (Compiladores)

Gramática completa, tokens e regras semânticas: **[GRAMATICA.md](GRAMATICA.md)**.

```
agente guarda sprite "guarda.png" em (300, 560) camada 2 {
    vivo.                       // crenças iniciais
    vida(3).
    patrulhando.

    +vivo <- velocidade(90, 0).                       // evento <- ações
    +borda : patrulhando <- inverter.                 // evento : contexto <- ações
    +jogador_perto : vivo <- -patrulhando; perseguir(jogador, 125).
    -jogador_perto : vivo <- +patrulhando; velocidade(90, 0).
    +recebeu_dano : vida(V) & V > 1 <- -+vida(V - 1); rotacionar(30).
    +recebeu_dano : vida(1) <- -vivo; parar; sumir; pontuar(50).
}

agente guarda2 : guarda sprite "guarda.png" em (980, 140) {   // herança
    +vivo <- velocidade(0, 110).                              // sobrescreve
}
```

### Ações da engine

| Ação | Efeito |
|---|---|
| `mover(dx, dy)` / `posicionar(x, y)` | desloca / coloca o sprite |
| `rotacionar(g)` / `girar(g_por_s)` | gira uma vez / rotação contínua |
| `escalar(f)` | multiplica a escala |
| `velocidade(vx, vy)` / `inverter` / `parar` | movimento contínuo |
| `perseguir(alvo, v)` / `fugir(alvo, v)` | segue / foge de outro objeto |
| `mudar_camada(n)` | muda a ordem de desenho |
| `cor(r, g, b)` | tinta (0 a 1) |
| `sumir` / `aparecer` | visibilidade |
| `imprimir(...)` | escreve no log (HUD e console) |

O jogo acrescenta `atacar(jogador, n)` e `pontuar(n)`, e gera as percepções
`jogador_perto`, `tocando_jogador`, `borda` e `recebeu_dano`. A crença
`raio_visao(N)`, se existir, é lida pelo jogo como raio de visão do agente.
Esse contrato fica em `jogo.py` (`PERCEPCOES`, `ACOES_JOGO`, `ALVOS`) e é
passado à análise semântica, que usa as assinaturas para checar aridade e tipos.

### Fases do compilador

| Fase | Arquivo | Destaques |
|---|---|---|
| Léxico | `lexer.py` | escrito à mão (AFD, maior lexema), posição linha:coluna, recuperação de erro |
| Sintático | `parser.py` | descendente recursivo LL(1), uma função por não terminal, modo pânico (relata vários erros) |
| AST | `ast.py` | dataclasses; `python -m agentdsl ast` imprime a árvore |
| Semântico | `semantica.py` | tabela de símbolos com escopos, herança, ligação de variáveis, inferência e checagem de tipos, sugestão "quis dizer…?" |
| Execução | `interpretador.py` | base de crenças, fila de eventos, unificação, contexto com backtracking, negação por falha |
| Integração | `ponte_engine.py` | ações → sprites, percepções → crenças (só as diferenças viram eventos) |

## Resultados (AMD Radeon Vega 8 integrada, Python 3.13, 20/11/2026)

Arquivos completos em `resultados/` (CSV com média, desvio, IC95%, p95; gráficos PNG).

**Engine: tempo por quadro (ms, 1280×720, sprites animados, vsync desligado, com glFinish)**

| sprites | individual | lote | lote_agrupado | lote_atlas |
|---:|---:|---:|---:|---:|
| 100 | 5,9 | 7,0 | 3,3 | **2,0** |
| 1 000 | 35,8 | 41,7 | 8,3 | **7,4** |
| 5 000 | 156,6 | 189,9 | 28,1 | **27,0** |
| 20 000 | 578,4 | 773,4 | 122,9 | **115,3** |
| 50 000 | 1 446 | 1 866 | 305,6 | **290,7** |

- O custo é dominado pelas **chamadas OpenGL feitas do Python** (~30 µs por draw call no
  PyOpenGL). Com texturas intercaladas, o "lote" quase não agrupa nada (799 draw calls para
  1 000 sprites) e fica pior que o individual. Agrupar por textura (20 draw calls) ou usar atlas
  (1 draw call) deixa até ~5× mais rápido; 60 FPS se mantêm até ~2 000 sprites animados.
- A resolução (800×600 a 1920×1080, 5 000 sprites) praticamente não muda o tempo: o gargalo
  é a CPU (atualização em Python + preparo dos dados), não o preenchimento de pixels na GPU.

**DSL**

| medida | valor |
|---|---|
| Front-end (programa com 1 000 agentes, 116 mil tokens) | léxico 809 ms · sintático 192 ms · semântico 79 ms |
| Interpretador | ~156–200 mil eventos/s (10 a 1 000 agentes) |
| Concisão (comportamento dos 2 guardas) | DSL: 22 linhas / 201 tokens · Python: 43 linhas / 347 tokens |

O léxico é a fase mais lenta (lê caractere a caractere em Python). A versão em Python do
guarda (`comparacao/guarda_em_python.py`) precisa guardar o estado anterior à mão para
detectar mudanças; na DSL isso é feito pela geração automática de eventos `+b`/`-b`.
