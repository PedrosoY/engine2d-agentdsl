# Engine2D + AgentDSL

Projeto único para duas disciplinas de Engenharia de Computação (FHO):

| Disciplina | Parte do projeto | Onde está |
|---|---|---|
| **Computação Gráfica** | Engine 2D em Python + OpenGL 3.3 com arquitetura no estilo Unity/Godot: GameObjects, componentes, hierarquia de transformações, física com grade espacial, câmera, UI, **editor dentro do jogo**, renderização em lote/atlas e **view frustum culling** | `engine2d/`, `demo_engine.py`, `benchmark_engine.py` |
| **Teoria da Computação e Compiladores** | AgentDSL: linguagem orientada a eventos inspirada em AgentSpeak/Jason (crenças → eventos → planos → ações), com lexer, parser LL(1), análise semântica com tipos e interpretador. Controla os inimigos, torres, armas e ondas dos jogos | `agentdsl/`, `GRAMATICA.md`, `jogos/*/*.agt`, `benchmark_dsl.py` |

Dois jogos completos mostram as duas partes funcionando juntas:

| Jogo | Estilo | Comportamento em DSL |
|---|---|---|
| **Arena dos Sobreviventes** (`jogos/arena`) | Vampire Survivors | 5 tipos de inimigo (com herança), chefe com 2 fases, 3 armas que sobem de nível, 2 "diretores" de ondas |
| **Defesa da Base** (`jogos/torres`) | Bloons TD | 7 inimigos que se dividem ao morrer (tanque → soldados), 4 torres com 3 níveis de melhoria, 15 ondas + modo infinito |

```
 jogos/arena/arena.agt ─► Lexer ─► Parser ─► AST ─► Semântica ─► Interpretador
                                                                   │   ▲
                                              ações (atirar, perseguir…)   percepções (+atingido(D), +onda(N)…)
                                                                   ▼   │
 engine2d:  GameObjects + Componentes ─► Física ─► sincroniza sprites ─► culling ─► lote/instancing ─► OpenGL
```

A engine não sabe o que é crença ou plano; a DSL não sabe o que é OpenGL. Elas
se encontram em `agentdsl/componente.py` (`ServicoAgentes` e `ComportamentoAgente`).

## Instalação e uso

Python 3.10+ e placa de vídeo/driver com OpenGL 3.3.

```powershell
pip install -r requirements.txt
```
```powershell
python jogar.py
```
Abre o menu com os dois jogos (`python jogar.py arena` ou `python jogar.py torres` vão direto).

| Tecla | Arena | Defesa da Base |
|---|---|---|
| WASD / setas | mover | — |
| mouse | — | comprar (painel), posicionar, selecionar torre |
| 1–4 | escolher melhoria | escolher torre |
| espaço | — | iniciar onda |
| ESC | pausa | cancela / pausa |
| **F1** | **editor** | **editor** |
| F2 | reinicia | reinicia |

```powershell
python -m agentdsl verificar jogos/arena/arena.agt
```
CLI da DSL: `tokens`, `ast`, `simbolos`, `verificar`, `executar` (sem gráficos), `jogo`.
Ela lê o "contrato" do jogo (ações, percepções) do `.py` com o mesmo nome do `.agt`.
Exemplos com erros de propósito em `exemplos/invalidos/`.

```powershell
python -m pytest
```
54 testes (use `-m "not gpu"` numa máquina sem OpenGL).

```powershell
python benchmark_engine.py
```
```powershell
python benchmark_dsl.py
```
Geram os CSVs e gráficos de `resultados/` usados nos artigos.

---

## Parte 1 — Engine2D (Computação Gráfica)

### Como se usa (parecido com a Unity)

```python
from engine2d import Motor, Cena, Componente, SpriteRenderer, CorpoRigido, Colisor

class Jogador(Componente):                 # equivale a um MonoBehaviour
    CAMPOS = {"velocidade": "float"}        # aparece e é editável no inspector
    velocidade = 200.0

    def iniciar(self):                      # Start()
        self.rb = self.obter(CorpoRigido)   # GetComponent<Rigidbody2D>()

    def atualizar(self, dt):                # Update()
        dx, dy = self.motor.entrada.direcao_wasd()
        self.rb.vx, self.rb.vy = dx * self.velocidade, dy * self.velocidade

    def ao_entrar_colisao(self, outro):     # OnTriggerEnter2D()
        print("encostou em", outro.gameobject.nome)

cena = Cena()
cena.criar("jogador", 640, 360, componentes=[
    SpriteRenderer(imagem="kenney_shooter/PNG/Survivor 1/survivor1_gun.png"),
    CorpoRigido(), Colisor(raio=18), Jogador()])
Motor(pasta_assets="assets").executar(cena)
```

| Conceito Unity | Engine2D | Arquivo |
|---|---|---|
| GameObject / Transform (hierarquia) | `GameObject`, `Transform` (pose local; mundo = pai ∘ local) | `objeto.py` |
| MonoBehaviour (Start, Update, LateUpdate, OnTrigger, OnGUI, OnDestroy) | `Componente` (`iniciar`, `atualizar`, `atualizar_tardio`, `ao_entrar_colisao`, `desenhar_ui`, `ao_destruir`) | `objeto.py` |
| Scene, Find, Destroy, Instantiate, prefab | `Cena` (`encontrar`, `destruir`, `instanciar`, prefabs em dict/JSON, cena salva em JSON) | `cena.py` |
| SpriteRenderer, Rigidbody2D, Collider2D, Animator | `SpriteRenderer`, `CorpoRigido`, `Colisor` (círculo/caixa, gatilho, camadas), `Animador` | `componentes.py` |
| Physics2D (layers, OverlapCircle) | `Fisica`: grade espacial, MTV, eventos entrar/sair, `consultar_circulo` | `fisica.py` |
| Input | `Entrada` (teclas, eixos, mouse em tela/mundo) | `entrada.py` |
| OnGUI / Canvas | `CamadaUI` (modo imediato: texto, barras, botões, janelas modais) | `ui.py` |
| Editor (Hierarchy, Inspector, Scene view, Play/Pause) | `Editor` (F1) | `editor.py` |

### Editor (F1, em qualquer cena)

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
| Integração | `componente.py` | `ServicoAgentes` (temporizadores, invocações, ciclo no LateUpdate) e `ComportamentoAgente` (ações → GameObject, percepções → crenças) |

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
