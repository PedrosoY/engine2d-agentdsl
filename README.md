# Engine2D + AgentDSL

Projeto único para duas disciplinas de Engenharia de Computação (FHO):

| Disciplina | Parte do projeto | Onde está |
|---|---|---|
| **Computação Gráfica** | Engine 2D em Python + OpenGL 3.3: GameObjects e componentes, hierarquia de transformações, iluminação 2D com sombras, física com grade espacial, câmera, UI, **editor dentro do jogo**, renderização em lote/atlas e **view frustum culling** | `engine2d/`, `demo_engine.py`, `benchmark_engine.py` |
| **Teoria da Computação e Compiladores** | AgentDSL: linguagem orientada a eventos inspirada em AgentSpeak/Jason (crenças → eventos → planos → ações), com lexer, parser LL(1), análise semântica com tipos e interpretador. Controla os inimigos, torres, armas e ondas dos jogos | `agentdsl/`, `GRAMATICA.md`, `Projeto*/Assets/Agentes/*.agt`, `benchmark_dsl.py` |

Três jogos completos mostram as duas partes funcionando juntas:

| Jogo | Estilo | Comportamento em DSL |
|---|---|---|
| **Arena dos Sobreviventes** (`ProjetoArena/`) | Vampire Survivors | 5 tipos de inimigo (com herança), chefe com 2 fases, 3 armas que sobem de nível, 2 "diretores" de ondas |
| **Defesa da Base** (`ProjetoTorres/`) | Bloons TD | 7 inimigos que se dividem ao morrer (tanque → soldados), 4 torres com 3 níveis de melhoria, 15 ondas + modo infinito |
| **Fábrica de Sorvete** (`ProjetoSorveteria/`) | The Farmer Was Replaced + Papa's Freezeria | começa com a fábrica vazia; o jogador **programa os robôs em janelas de código flutuantes** (uma para todos ou uma por robô); cada sorvete passa por casquinha → sorvete → massa → bater → calda → coberturas, e **qualquer etapa pode falhar** (tratada com objetivos `+!g`/`-!g`); árvore com estações, cardápio e partes da linguagem; **robôs passam o sorvete pela bancada** (multiagente) e um gerente compra sozinho; erros comuns com mensagem de iniciante |

```
 arena.agt (DSL)       ─► Lexer ─► Parser ─► AST ─► Semântica ─► Interpretador
                                                                   │   ▲
                                              ações (atirar, perseguir…)   percepções (+atingido(D), +onda(N)…)
                                                                   ▼   │
 engine2d:  GameObjects + Componentes ─► Física ─► sincroniza sprites ─► culling ─► lote/instancing ─► OpenGL
```

A engine não sabe o que é crença ou plano; a DSL não sabe o que é OpenGL. Elas
se encontram em `agentdsl/componente.py` (`ServicoAgentes` e `ComportamentoAgente`).

## Começando

> **Novo aqui?** Leia o [TUTORIAL.md](TUTORIAL.md): tour do editor, scripts, prefabs, física, UI e a AgentDSL,
> refazendo do zero o Coletor de Moedas passo a passo.

```powershell
pip install -r requirements.txt
```
```powershell
python editor.py
```

Abre o **editor**. Na tela inicial clique em **"Abrir o projeto de exemplo"** (ou crie um projeto novo).
A janela abre maximizada; arraste as bordas entre os painéis para mudar o tamanho deles.

| Painel | Onde | Como usar |
|---|---|---|
| Hierarchy | esquerda | clique seleciona · arraste um objeto sobre outro = vira filho · botão direito = criar/renomear/excluir |
| Scene | centro | W/E/R = mover/girar/escalar · botão do meio ou direito arrasta · roda = zoom · F = focar |
| Inspector | direita | edite os valores (clique e digite, ou arraste sobre o nome do campo) · **Adicionar Componente** |
| Project | embaixo | pastas do projeto · botão direito → **Criar → Script** · clique duplo abre no VS Code |
| Console | aba embaixo | mensagens, erros dos scripts e os `print()` do jogo |
| **► Play** | barra de cima (Ctrl+P) | roda a cena atual numa janela |
| Atalhos | — | Ctrl+S salva a cena · Ctrl+Z desfaz (Ctrl+Y refaz) · Ctrl+D duplica · Del exclui |

### Criar um script

1. No Project, botão direito na pasta **Scripts → Criar Script**, dê um nome (ex.: `Jogador`).
2. Clique duas vezes no arquivo: ele abre no VS Code já com um modelo pronto:

```python
from engine2d import Componente

class Jogador(Componente):
    CAMPOS = {"velocidade": "float"}     # aparece no Inspector para editar
    velocidade = 200.0

    def iniciar(self):                   # roda uma vez, antes do primeiro quadro
        pass

    def atualizar(self, dt):             # roda todo quadro (dt = segundos desde o último)
        dx, dy = self.motor.entrada.direcao_wasd()
        self.transform.x += dx * self.velocidade * dt
        self.transform.y += dy * self.velocidade * dt
```

3. Salve. O editor recarrega sozinho. Selecione um objeto → **Adicionar Componente → Scripts → Jogador**.
4. **► Play**.

| Para | Código |
|---|---|
| pegar outro componente do mesmo objeto | `self.obter(CorpoRigido)` |
| achar um objeto pelo nome | `self.cena.encontrar("jogador")` |
| posição | `self.transform.x`, `self.transform.y` (ou `posicao_mundo`) |
| tecla apertada | `self.motor.entrada.tecla("space")` |
| destruir o objeto | `self.gameobject.destruir()` |
| criar a partir de um prefab | `self.cena.instanciar("Assets/Prefabs/x.prefab", x, y)` |
| reagir a uma colisão | `def ao_entrar_colisao(self, outro):` |
| escrever no Console | `print("oi")` |

### Organização de um projeto

```
MeuJogo/
  projeto.json            nome, cena inicial, tamanho da janela
  Assets/
    Cenas/*.cena          cenas (JSON)
    Scripts/*.py          seus scripts (componentes)
    Sprites/*.png         imagens (arraste do Windows para dentro do editor para importar)
    Prefabs/*.prefab      objetos prontos (arraste um objeto da Hierarchy para o Project)
    Agentes/*.agt         comportamentos na AgentDSL
  Library/                arquivos temporários do editor (pode apagar)
```

Para rodar um projeto sem o editor: `python rodar.py MeuJogo`.

### O projeto de exemplo ("Coletor de Moedas")

`ProjetoExemplo/` — o jogador (WASD) pega moedas enquanto zumbis o perseguem.
- `Assets/Scripts/Jogador.py`, `Moeda.py`, `Placar.py`: scripts comentados.
- `Assets/Agentes/inimigos.agt`: zumbis e ondas escritos na AgentDSL.
- `Assets/Scripts/AcoesDSL.py`: cria a ação `avisar(...)` para a DSL a partir do Python (`@acao_dsl`).
- A câmera é filha do jogador na Hierarchy (por isso segue ele).

### Os dois jogos completos

Também são projetos do editor, prontos para abrir pela tela inicial (ou `python editor.py ProjetoArena`):

| Projeto | O que tem |
|---|---|
| `ProjetoArena/` — Arena dos Sobreviventes (estilo Vampire Survivors) | `Assets/Agentes/arena.agt` com inimigos, chefe, armas e ondas; scripts `Jogador`, `Inimigo`, `Armas`, `Gema`, `GerenteArena`, `Comum`; um prefab por inimigo |
| `ProjetoTorres/` — Defesa da Base (estilo Bloons TD) | `Assets/Agentes/torres.agt` com inimigos que se dividem, torres e melhorias, 15 ondas; scripts `Mapa`, `Inimigos`, `Torres`, `GerenteTD`, `Comum`; prefabs de inimigos e torres |
| `ProjetoPlataforma/` — Pulo Verde (plataforma estilo Mario) | montado pelo editor (`montar_plataforma.py`); fase em `Assets/Fases/fase1.mapa` (componente `MapaTiles`); física com gravidade, chão, paredes e plataformas atravessáveis; `plataforma.agt` com slime, caracol, abelha, sapo, blocos "?" e o agente da fase; arte Kenney *New Platformer Pack* (CC0) |
| `ProjetoNavinha/` — Navinha (shoot 'em up) | montado inteiro pelo editor (`montar_navinha.py` + robô do editor); `Assets/Agentes/navinha.agt` com 6 inimigos (herança), chefe de 3 fases e o diretor das ondas; partículas, fundo rolante e som; arte Kenney *Space Shooter Redux* (CC0) |
| `ProjetoSorveteria/` — Fábrica de Sorvete | scripts `Robo` (fila de comandos, pilha de objetivos, falhas), `Fabrica` (pedidos e nota), `Painel`/`Janelas` (janelas flutuantes, compilação por janela), `Desbloqueios` (árvore + verificação da AST), `Erros` (mensagens amigáveis), `Tutorial`; `Solucoes/` tem um programa por fase; gerado por `gerar_sorveteria.py` |

Para só jogar, sem o editor: `python jogar.py` (menu com todos os projetos) ou `python rodar.py ProjetoArena`.
Os jogos abrem em tela cheia: o jogo é desenhado num framebuffer (FBO) na resolução dele e ampliado para o
monitor mantendo a proporção (`--janela` abre numa janela).
Um script pode importar outro do mesmo projeto (`from Comum import painel_fim`).

### Testes e medições

```powershell
python -m pytest
```
```powershell
python benchmark_engine.py
```

---

## Parte 1 — Engine2D (Computação Gráfica)

### Como se usa

```python
from engine2d import Motor, Cena, Componente, SpriteRenderer, CorpoRigido, Colisor

class Jogador(Componente):                 # um comportamento é um componente
    CAMPOS = {"velocidade": "float"}        # aparece e é editável no inspector
    velocidade = 200.0

    def iniciar(self):                      # antes do primeiro quadro
        self.rb = self.obter(CorpoRigido)   # outro componente do mesmo objeto

    def atualizar(self, dt):                # todo quadro
        dx, dy = self.motor.entrada.direcao_wasd()
        self.rb.vx, self.rb.vy = dx * self.velocidade, dy * self.velocidade

    def ao_entrar_colisao(self, outro):     # quando encosta em outro colisor
        print("encostou em", outro.gameobject.nome)

cena = Cena()
cena.criar("jogador", 640, 360, componentes=[
    SpriteRenderer(imagem="kenney_shooter/PNG/Survivor 1/survivor1_gun.png"),
    CorpoRigido(), Colisor(raio=18), Jogador()])
Motor(pasta_assets="assets").executar(cena)
```

| Peça | O que faz | Arquivo |
|---|---|---|
| `GameObject`, `Transform` | objeto da cena e sua pose local; mundo = pai ∘ local (hierarquia) | `objeto.py` |
| `Componente` | comportamento: `iniciar`, `atualizar`, `atualizar_tardio`, `ao_entrar_colisao`, `desenhar_ui`, `ao_destruir` | `objeto.py` |
| `Cena` | `encontrar`, `destruir`, `instanciar`, prefabs, cena salva em JSON | `cena.py` |
| `SpriteRenderer`, `CorpoRigido`, `Colisor`, `Animador`, `Luz2D`... | desenho, física (círculo/caixa, gatilho, camadas), animação, luz | `componentes.py` |
| `Fisica` | gravidade, grade espacial, MTV, eventos entrar/sair, raios | `fisica.py` |
| `Entrada` | teclas, eixos, mouse em tela/mundo | `entrada.py` |
| `CamadaUI` | interface em modo imediato: texto, barras, botões, janelas | `ui.py` |
| `Editor` (F1) | inspetor de depuração dentro do jogo | `editor.py` |

### Inspetor de depuração (F1, dentro dos jogos de demonstração)

- **Hierarquia** (esquerda): árvore de objetos, nós recolhíveis (+/−), clique seleciona.
- **Inspector** (direita): Transform e todos os componentes com seus campos editáveis
  (clique e digite; roda do mouse soma/subtrai; caixa liga/desliga o componente).
  Para objetos controlados pela DSL, mostra as **crenças atuais e os últimos eventos** do agente.
- **Cena**: clique seleciona, arraste move, botão direito arrasta a câmera, roda dá zoom,
  F foca a câmera no selecionado, gizmos de seleção (caixa + eixos locais) e de colisores (G liga/desliga).
- **Barra**: Play/Pause (F5), Passo (F6), Salvar/Carregar cena em JSON (Ctrl+S / Ctrl+L),
  Novo, Duplicar (Ctrl+D), Excluir (Del), FPS, draw calls e tempos.

### Pipeline de renderização

Sprite → transformação M = T·R·S → **culling** → agrupamento → vertex shader → rasterização → fragment shader

- **Ordem por camadas**: lista ordenada de forma estável (L_A < L_B ⇒ A antes), reordenada só quando algo muda.
- **Modos de desenho** (comparados no benchmark): `individual` (1 draw call por sprite, o pipeline do artigo),
  `lote` (instancing por sequências de mesma textura), `lote_agrupado` (ordena por textura dentro da camada)
  e `lote_atlas` (todas as imagens numa textura: a cena inteira em 1 draw call).
- **View frustum culling** (Eixo 2, Assarsson): cada sprite vira um círculo envolvente e é descartado se não
  toca o retângulo visível da câmera — teste vetorizado no numpy (`renderizador.py`).
- **Sprites estáticos**: cenário marcado `estatico=True` não recalcula a pose a cada quadro.
- **UI**: uma Surface do pygame enviada à GPU sem cópia (buffer BGRA direto no `glTexSubImage2D`), invertida pelo próprio sprite (sy = −1).
- **Ordem de desenho**: chave (camada de desenho, ordem na camada, ordem na Hierarchy).
- **Iluminação 2D** (`Luz2D`, `ProjetorSombra2D`): 1) mapa de luz num FBO RGBA16F com stencil, limpo com a luz
  global; 2) cada luz (ponto ou cone) é um quad com atenuação suave somado por mistura aditiva
  (`GL_ONE, GL_ONE`); 3) sombras por **volumes de sombra 2D**: os polígonos do objeto até longe da luz marcam o
  stencil e a luz só é desenhada onde ele é 0; 4) o fragment shader dos sprites multiplica a cor pela luz do
  pixel (`gl_FragCoord` → coordenada no mapa de luz). Sprites com `receber_luz = False` ignoram as luzes e
  `aditivo = True` usa `GL_SRC_ALPHA, GL_ONE` (brilho), agrupando os lotes por textura e modo de mistura.
- **Tela cheia**: o jogo é desenhado num FBO na sua resolução e esse quadro é ampliado para o monitor.

## Parte 2 — AgentDSL (Compiladores)

Gramática (EBNF), tokens, regras semânticas e semântica de execução: **[GRAMATICA.md](GRAMATICA.md)**.

```
// Tipo de inimigo: cada zumbi que nasce é uma instância com suas próprias crenças.
modelo zumbi {
    nasceu.  vida(10).  dano(8).  xp(1).

    +nasceu <- perseguir(jogador, 75).
    +atingido(D) : vida(V) & V > D  <- -+vida(V - D); piscar.
    +atingido(_D) : xp(X)           <- soltar_xp(X); morrer.
    +tocando_jogador : dano(X) <- ferir_jogador(X); temporizador(0.8, morder).
    +morder : tocando_jogador & dano(X) <- -morder; ferir_jogador(X); temporizador(0.8, morder).
    +morder <- -morder.
}

modelo corredor : zumbi {            // herança: muda só os números
    vida(7).
    +nasceu <- perseguir(jogador, 140).
}

// Uma arma: o jogo troca nivel(N) por nivel(N+1) quando o jogador escolhe a melhoria.
agente pistola {
    nivel(1).
    +nivel(1) <- temporizador(0.4, pronta).
    +pronta : nivel(N) <- -pronta; atirar_mais_proximo(8 + 3 * N, 600, 1 + N / 2, 1 + N / 3);
                          temporizador(0.75 - 0.1 * N, pronta).
}

// Diretor de ondas: o primeiro plano aplicável vence; % = resto da divisão.
agente elite {
    +segundo(S) : S >= 60 & S % 20 == 0 <- invocar(corredor, 8); imprimir("Bando de corredores!").
}
```

| Fase | Arquivo | Destaques |
|---|---|---|
| Léxico | `lexer.py` | escrito à mão (AFD, maior lexema), linha:coluna, recuperação de erro, tolera BOM |
| Sintático | `parser.py` | descendente recursivo LL(1), uma função por não terminal, modo pânico (vários erros por execução) |
| AST | `ast.py` | `python -m agentdsl ast` imprime a árvore |
| Semântico | `semantica.py` | tabela de símbolos com escopos, herança, `agente` × `modelo`, ligação de variáveis, inferência e checagem de tipos (incl. `modelo`/`crenca`), sugestões "quis dizer…?" |
| Execução | `interpretador.py` | instâncias de modelos, fila de eventos, unificação, contexto com backtracking, negação por falha, erros de execução isolados |
| Integração | `componente.py` | `ServicoAgentes` (temporizadores, invocações, ciclo em `atualizar_tardio`) e `ComportamentoAgente` (ações → GameObject, percepções → crenças) |

## Resultados (AMD Radeon Vega 8 integrada, Python 3.13, 20/11/2026)

CSVs completos (média, desvio, IC95%, p95) e gráficos em `resultados/`.

**Modos de desenho** — ms por quadro, 1280×720, sprites animados, vsync desligado, com `glFinish`:

| sprites | individual | lote | lote_agrupado | lote_atlas |
|---:|---:|---:|---:|---:|
| 1 000 | 33,3 | 41,2 | 8,1 | 8,2 |
| 5 000 | 153 | 187 | 27,8 | 25,3 |
| 20 000 | 596 | 746 | 116 | 118 |

O custo é dominado pelas chamadas OpenGL feitas do Python (~30 µs por draw call). Com
texturas intercaladas, o "lote" quase não agrupa (799 draw calls para 1 000 sprites) e fica pior que o
individual; agrupar por textura ou usar atlas (20 → 1 draw call) é ~5× mais rápido. A resolução
(800×600 a 1920×1080) quase não muda o tempo: o gargalo é a CPU, não o preenchimento de pixels.

**View frustum culling** — 20 000 sprites espalhados num mundo de N×N telas (lote_atlas):

| mundo | sem culling | com culling | descartados |
|---|---:|---:|---:|
| 1×1 | 108,8 ms | 142,2 ms | 0 % |
| 2×2 | 98,7 ms | 81,4 ms | 73 % |
| 4×4 | 101,0 ms | 69,1 ms | 93 % |
| 8×8 | 100,6 ms | 66,8 ms | 98 % |

Com tudo na tela o culling só custa (o teste em Python percorre todos os sprites); a partir de
um mundo 2×2 ele compensa. O restante do tempo é a atualização dos 20 000 objetos em Python.

**Física (fase ampla com grade espacial)** — GameObjects com SpriteRenderer + CorpoRigido + Colisor:

| objetos | pares testados | força bruta n(n−1)/2 | redução | ms física |
|---:|---:|---:|---:|---:|
| 100 | 87 | 4 950 | 57× | 2,1 |
| 500 | 453 | 124 750 | 275× | 9,6 |
| 2 000 | 1 976 | 1 999 000 | 1 012× | 43,8 |

**Jogos** (simulações automáticas): Arena com ~110 inimigos vivos: p50 10,6 ms/quadro; Defesa da Base
nas ondas finais: p50 10,2 ms, p95 16,4 ms.

**AgentDSL**

| medida | valor |
|---|---|
| Front-end, programa com 1 000 agentes (116 mil tokens) | léxico 707 ms · sintático 175 ms · semântico 81 ms |
| Interpretador | 178–217 mil eventos/s (10 a 1 000 agentes) |
| Concisão: `zumbi` + `atirador` | DSL 23 linhas / 217 tokens · Python equivalente 61 linhas / 382 tokens |

A versão em Python (`comparacao/inimigos_em_python.py`) precisa guardar o valor anterior de cada
percepção para detectar mudanças e controlar temporizadores à mão; na DSL isso vem dos eventos
`+b`/`-b` e de `temporizador(...)`.

## Créditos

Arte: [Kenney](https://kenney.nl) — *Top-down Shooter* e *Tower Defense (Top-Down)*,
licença CC0 (domínio público). Os efeitos `anel.png`, `brilho.png` e `sombra.png`
são gerados por código.
