# Gramática da AgentDSL

Gramática livre de contexto G = (V, Σ, P, S), com S = `programa`, em EBNF.
`{ x }` = zero ou mais repetições, `[ x ]` = opcional, `|` = alternativa.
É LL(1): o parser descendente recursivo (`agentdsl/parser.py`) decide cada
regra olhando só o próximo token.

```ebnf
programa     = { agente } ;

agente       = "agente" IDENT [ ":" IDENT ] [ decl_sprite ]
               "{" { crenca | plano } "}" ;
decl_sprite  = "sprite" TEXTO [ "em" "(" numero "," numero ")" ] [ "camada" numero ] ;
numero       = [ "-" ] NUM ;

crenca       = literal "." ;
plano        = evento [ ":" contexto ] "<-" corpo "." ;
evento       = ( "+" | "-" ) literal ;

contexto     = condicao { "&" condicao } ;
condicao     = "verdadeiro"
             | "nao" literal
             | literal
             | arg op_rel arg ;
op_rel       = "<" | "<=" | ">" | ">=" | "==" | "!=" ;

corpo        = acao { ";" acao } ;
acao         = ( "+" | "-" | "-+" ) literal      (* altera a base de crenças *)
             | IDENT [ "(" [ args ] ")" ] ;      (* ação enviada à engine    *)

literal      = IDENT [ "(" [ args ] ")" ] ;
args         = arg { "," arg } ;
arg          = TEXTO | expr ;
expr         = termo { ( "+" | "-" ) termo } ;
termo        = fator { ( "*" | "/" ) fator } ;
fator        = NUM | VAR | IDENT | "(" expr ")" | "-" fator ;
```

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
| reservadas | `agente sprite em camada nao verdadeiro` | |
| símbolos | `{ } ( ) , . ; : & + - * / < > <= >= == != <- -+` | |
| comentários | `//...` até o fim da linha, `/* ... */` | |

Regra do maior lexema: `<-` é um token só (não `<` seguido de `-`), assim
como `-+`, `<=`, `>=`, `==`, `!=`. Em `vida(3).` o número termina antes do
ponto porque a parte fracionária exige um dígito depois do `.`.

## Regras semânticas

1. Nomes de agentes são únicos; o agente pai (`agente filho : pai`) deve
   existir e ser declarado antes (o que também impede herança cíclica).
2. Crenças iniciais são fatos: não podem conter variáveis.
3. Escopo de variáveis = o plano. Uma variável é **ligada** quando aparece no
   evento ou num literal positivo do contexto; usá-la antes (numa ação, numa
   comparação ou num `nao`) é erro.
4. Ações externas precisam existir no catálogo da engine/aplicação e receber
   o número e os tipos certos de argumentos (`num`, `atomo`, `texto`).
5. Tipos das crenças são inferidos (crenças iniciais, percepções declaradas,
   `+lit` nos corpos) e precisam ser consistentes; variáveis herdam o tipo do
   argumento em que foram ligadas e passam a `num` quando usadas em conta.
6. Aritmética e `< <= > >=` só com números; divisão por zero constante é erro.
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
- `nao lit` é negação por falha: verdadeiro se nenhuma crença unifica.
- Cada agente processa no máximo N eventos por ciclo (padrão 64), o que
  impede que um laço de eventos trave o quadro da engine.
