# Gramática da AgentDSL

Gramática livre de contexto G = (V, Σ, P, S), com S = `programa`, em EBNF.
`{ x }` = zero ou mais repetições, `[ x ]` = opcional, `|` = alternativa.
É LL(1): o parser descendente recursivo (`agentdsl/parser.py`) decide cada
regra olhando só o próximo token.

```ebnf
programa     = { agente } ;

agente       = ( "agente" | "modelo" ) IDENT [ ":" IDENT ] [ decl_sprite ]
               "{" { crenca | plano } "}" ;
decl_sprite  = "sprite" TEXTO [ "em" "(" numero "," numero ")" ] [ "camada" numero ] ;
numero       = [ "-" ] NUM ;

crenca       = literal "." ;
plano        = evento [ ":" contexto ] "<-" corpo "." ;
evento       = ( "+" | "-" ) [ "!" ] literal ;     (* +!g novo objetivo, -!g o objetivo falhou *)

contexto     = condicao { "&" condicao } ;
condicao     = "verdadeiro"
             | "nao" literal
             | literal
             | arg op_rel arg ;
op_rel       = "<" | "<=" | ">" | ">=" | "==" | "!=" ;

corpo        = acao { ";" acao } ;
acao         = ( "+" | "-" | "-+" ) literal      (* altera a base de crenças *)
             | "!" literal                       (* persegue um objetivo: dispara +!literal *)
             | IDENT [ "(" [ args ] ")" ] ;      (* ação enviada à engine    *)

literal      = IDENT [ "(" [ args ] ")" ] ;
args         = arg { "," arg } ;
arg          = TEXTO | expr ;
expr         = termo { ( "+" | "-" ) termo } ;
termo        = fator { ( "*" | "/" | "%" ) fator } ;
fator        = NUM | VAR | IDENT | "(" expr ")" | "-" fator ;
```

`agente` declara uma instância única, criada quando o programa começa
(ex.: uma arma, o diretor de ondas). `modelo` declara um TIPO: nada é criado
no início; o jogo (ou a ação `invocar`) cria quantas instâncias quiser, cada
uma com a própria base de crenças (ex.: cada zumbi, cada torre).

Observação sobre `condicao`: quando começa com `IDENT`, o parser lê um
`literal`; se o token seguinte for um operador relacional, o literal (sem
argumentos) é reinterpretado como átomo do lado esquerdo da comparação.
Isso mantém a decisão com um token de lookahead.

## Tokens (léxico)

| Token | Expressão regular | Exemplo |
|---|---|---|
| IDENT | `[a-z][a-zA-Z0-9_]*` (exceto palavras reservadas) | `vivo`, `jogador_perto` |
| VAR | `[A-Z_][a-zA-Z0-9_]*` | `V`, `X`, `_Ignorado` |
| NUM | `[0-9]+(\.[0-9]+)?` | `3`, `0.85` |
| TEXTO | `"([^"\\\n]|\\.)*"` | `"guarda.png"` |
| reservadas | `agente modelo sprite em camada nao verdadeiro` | |
| símbolos | `{ } ( ) , . ; : & + - * / % < > <= >= == != <- -+ !` | |
| comentários | `//...` até o fim da linha, `/* ... */` | |

Regra do maior lexema: `<-` é um token só (não `<` seguido de `-`), assim
como `-+`, `<=`, `>=`, `==`, `!=`. Em `vida(3).` o número termina antes do
ponto porque a parte fracionária exige um dígito depois do `.`.

## Regras semânticas

1. Nomes de agentes e modelos são únicos; o pai (`modelo filho : pai`) deve
   existir e ser declarado antes (o que também impede herança cíclica).
2. Crenças iniciais são fatos: não podem conter variáveis.
3. Escopo de variáveis = o plano. Uma variável é **ligada** quando aparece no
   evento ou num literal positivo do contexto; usá-la antes (numa ação, numa
   comparação ou num `nao`) é erro.
4. Ações externas precisam existir no catálogo da engine/aplicação e receber
   o número e os tipos certos de argumentos (`num`, `atomo`, `texto`).
   Dois tipos especiais de parâmetro: `modelo` (o átomo precisa ser um `modelo`
   declarado — `invocar(zumbi, 3)`; usar um `agente` único dá erro) e `crenca`
   (nome de crença que a ação vai adicionar — `temporizador(1.5, pronta)` conta
   como fonte do evento `+pronta`).
5. Tipos das crenças são inferidos (crenças iniciais, percepções declaradas,
   `+lit` nos corpos) e precisam ser consistentes; variáveis herdam o tipo do
   argumento em que foram ligadas e passam a `num` quando usadas em conta.
6. Aritmética (`+ - * / %`) e `< <= > >=` só com números; divisão ou resto
   por zero constante é erro.
7. Avisos (não impedem a execução): evento que nunca será gerado, variável que
   aparece uma só vez, alvo de `perseguir`/`fugir` que não é agente nem objeto
   do ambiente, crença usada com aridades diferentes.

## Semântica de execução

- Adicionar uma crença que ainda não existe gera o evento `+b`; remover uma
  que existe gera `-b` (alterações que não mudam a base não geram evento).
- As crenças iniciais geram eventos `+b` ao iniciar (como no Jason).
- Para cada evento, os planos relevantes são testados **na ordem do código**
  (os do filho antes dos herdados); o primeiro cujo gatilho unifica e cujo
  contexto é satisfeito é executado inteiro.
- `-+lit` remove todas as crenças com o mesmo nome/aridade e adiciona `lit`.
- `nao lit` é negação por falha: verdadeiro se nenhuma crença unifica. Variáveis anônimas (`_X`) podem aparecer livres: `nao carregando(_X)` = não carrega nada.
- Cada agente processa no máximo N eventos por ciclo (padrão 64), o que
  impede que um laço de eventos trave o quadro da engine.
- Um erro em tempo de execução (ex.: divisão por zero com variáveis) é
  registrado no log e interrompe só aquele plano; o jogo continua.
- Na engine, o ciclo de raciocínio roda em `atualizar_tardio` (depois dos scripts do quadro):
  primeiro os componentes do jogo geram as percepções do quadro, depois os
  agentes reagem. Percepções que não mudaram não geram eventos; "pulsos"
  (como `atingido(D)`) entram num quadro e saem no seguinte.

## Ações da engine (disponíveis em qualquer jogo)

| Ação | Efeito |
|---|---|
| `mover(dx, dy)` / `posicionar(x, y)` | desloca / coloca o objeto |
| `rotacionar(g)` / `girar(g_por_s)` / `escalar(f)` | rotação única / contínua / escala |
| `velocidade(vx, vy)` / `inverter` / `parar` | movimento contínuo |
| `perseguir(alvo, v)` / `fugir(alvo, v)` | segue / foge de um objeto pelo nome |
| `mudar_camada(n)` / `cor(r, g, b)` / `piscar` | aparência |
| `trocar_imagem("x.png")` / `sumir` / `aparecer` | sprite |
| `temporizador(seg, crenca)` | após `seg` segundos adiciona a crença |
| `invocar(modelo, n)` / `invocar_aqui(modelo, n)` | cria instâncias (onde o jogo decidir / no lugar do agente) |
| `invocar_serie(modelo, n, intervalo)` | cria n instâncias, uma a cada `intervalo` segundos |
| `morrer` | destrói o GameObject (e a instância do agente) |
| `imprimir(...)` | escreve no log/HUD |

Cada jogo acrescenta as suas (ex.: `atirar`, `pagar`, `soltar_xp`) declarando
a assinatura em Python; a análise semântica usa essas assinaturas.


## Objetivos (estilo AgentSpeak / Jason)

Além de crenças, um agente pode ter **objetivos**. `+!g` é o evento "quero alcançar g"; o plano diz
como. `!g` no corpo de um plano persegue o objetivo; `-!g` é o evento "o objetivo g falhou".

```
+ligado <- !produzir_sorvete.
+!produzir_sorvete <- pegar_casquinha(medio); adicionar_sorvete(creme); entregar; !produzir_sorvete.
-!produzir_sorvete <- jogar_fora; !produzir_sorvete.
```

Regras semânticas: todo `!g` precisa de um plano `+!g` com a mesma aridade (senão é erro, com sugestão
de nome parecido); um `-!g` sem `+!g` gera aviso. Objetivos não são crenças: não entram na base de
crenças, só na fila de eventos. Se um `+!g` não tiver plano aplicável, o objetivo falha (o ambiente é
avisado por `sem_plano`). O ambiente também pode decidir *quando* o objetivo começa (`objetivo`): no
jogo da sorveteria o robô só começa `!g` depois dos comandos anteriores, e a falha de um comando sobe
pelos objetivos até achar um com plano `-!` (como a pilha de intenções do Jason).
