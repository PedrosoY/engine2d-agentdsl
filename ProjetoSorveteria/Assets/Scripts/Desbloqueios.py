"""Árvore de habilidades e o "pedágio" da linguagem.

Como no The Farmer Was Replaced, a linguagem é liberada aos poucos. No começo o programa só pode ter
objetivos (``+!produzir <- ...``, ``!produzir``, ``-!produzir <- ...``).
Condições, variáveis, operadores, crenças próprias, relógio, comunicação entre robôs e o gerente são
comprados na árvore, junto com estações, opções do cardápio e melhorias.

``verificar`` percorre a AST gerada pelo parser e devolve um erro (com linha e coluna) para cada
recurso ainda bloqueado.
"""
from agentdsl import ast as A
from agentdsl.erros import Diagnostico


class No:
    def __init__(self, titulo, custo, requisitos, desc, coluna, linha, niveis=1, mult=1.0, novidade="",
                 exemplo=""):
        self.titulo, self.custo, self.requisitos, self.desc = titulo, custo, requisitos, desc
        self.coluna, self.linha = coluna, linha
        self.niveis, self.mult = niveis, mult
        self.novidade, self.exemplo = novidade, exemplo


ARVORE = {
    # --- linguagem -------------------------------------------------------------------------------
    "sentidos": No("Sentidos", 30, [], "condições ':' e o que o robô percebe", 0, 1,
                   novidade="Um plano pode ter CONDIÇÃO (depois do ':'). O robô percebe livre, segurando(T),\n"
                            "tem_sorvete(S), tem_pedido, fila(N)... e eventos como +falhou(M) e +novo_pedido.",
                   exemplo="+!produzir : tem_pedido <- !montar.\n+!produzir <- perguntar_pedido; !montar."),
    "variaveis": No("Variáveis", 60, ["sentidos"], "nomes com MAIÚSCULA guardam valores", 1, 1,
                    novidade="Variáveis começam com maiúscula e pegam o valor de uma percepção.\n"
                             "Ex.: depois de perguntar_pedido, pedido_sabor(S) diz o sabor que o cliente quer.",
                    exemplo="+!montar : pedido_sabor(S) <- pegar_casquinha; adicionar_sorvete(S); entregar."),
    "operadores": No("Operadores", 60, ["sentidos"], "nao, ==, !=, <, >, + - * /", 2, 1,
                     novidade="Comparações (==, !=, <, >, <=, >=), contas (+ - * / %) e a negação 'nao'.",
                     exemplo="+!cobrir : pedido_cobertura(C) & nao tem_cobertura(C) <- adicionar_cobertura(C); !cobrir."),
    "memoria": No("Memória", 60, [], "crenças próprias: +nota / -nota", 0, 5,
                  novidade="O robô pode lembrar coisas: crenças iniciais (ex.: feitos(0).) e ações +crenca,\n"
                           "-crenca e -+crenca no corpo. Cada crença nova gera um evento +crenca.",
                  exemplo="feitos(0).\n+entregou(_V) : feitos(N) <- -+feitos(N + 1)."),
    "relogio": No("Relógio", 50, ["memoria"], "esperar(seg) e temporizador(seg, c)", 1, 5,
                  novidade="esperar(2) para o robô por 2 s. temporizador(5, acordar) cria a crença 'acordar'\n"
                           "daqui a 5 s (gera +acordar).",
                  exemplo="-!produzir <- jogar_fora; esperar(1); !produzir."),
    "comunicacao": No("Comunicação", 180, ["robos", "memoria"], "avisar(robo2, recado): robôs conversam", 4, 5,
                      novidade="avisar(robo2, pronto) faz o robo2 perceber +recado(pronto).\n"
                               "Junte com as bancadas para um robô avisar o outro quando o sorvete está lá.",
                      exemplo="// robo1\n+!base <- pegar_casquinha; adicionar_sorvete(creme); deixar(bancada1);\n"
                              "    avisar(robo2, pronto); !base.\n// robo2\n+recado(pronto) <- pegar_de(bancada1); entregar."),
    "gerencia": No("Gerência", 500, ["comunicacao", "operadores"], "uma janela 'gerente' que compra sozinha",
                   5, 5, novidade="Crie uma janela de código para o GERENTE (escolha 'gerente' no alto da janela).\n"
                                  "Ele percebe dinheiro(D), preco(Item, P), robos(N), clientes(N) e usa comprar(item).",
                   exemplo="+dinheiro(D) : preco(manutencao, P) & D >= P <- comprar(manutencao)."),
    # --- estações (cada uma acrescenta uma etapa aos pedidos e vale mais) -------------------------------
    "massas": No("Estação de massas", 70, [], "adicionar_massa(morango)", 1, 2,
                 novidade="Nova estação: MASSAS. Agora os clientes pedem uma massa misturada (+$3).\n"
                          "Comando: adicionar_massa(morango) — antes de bater!",
                 exemplo="+!montar <- pegar_casquinha; adicionar_sorvete(creme); adicionar_massa(morango); entregar."),
    "batedeira": No("Batedeira", 150, ["massas"], "bater(pouco | medio | bem)", 2, 3,
                    novidade="Nova estação: BATEDEIRA. Cada cliente pede um ponto: pouco, medio ou bem.\n"
                             "Leia pedido_ponto(P) e use bater(P). Cuidado: às vezes passa do ponto!",
                    exemplo="+!bater : pedido_ponto(P) <- bater(P)."),
    "caldas": No("Caldas", 220, ["batedeira"], "adicionar_calda(chocolate)", 3, 3,
                 novidade="Nova estação: CALDAS. Leia pedido_calda(C) e use adicionar_calda(C). Pode entupir!",
                 exemplo="+!calda : pedido_calda(C) <- adicionar_calda(C)."),
    "coberturas": No("Coberturas", 320, ["caldas"], "adicionar_cobertura(chantilly)", 4, 4,
                     novidade="Nova estação: COBERTURAS. Cada cliente pede 1 ou 2: pedido_cobertura(C).\n"
                              "adicionar_cobertura(chantilly). Pode escorregar!",
                     exemplo="+!cobrir : pedido_cobertura(C) & nao tem_cobertura(C) <- adicionar_cobertura(C); !cobrir.\n"
                             "+!cobrir <- entregar."),
    # --- cardápio -----------------------------------------------------------------------------------
    "tamanhos": No("Tamanhos P e G", 50, ["variaveis"], "casquinhas pequeno e grande", 1, 0,
                   novidade="Clientes agora pedem tamanhos: pequeno ($5), medio ($7) e grande ($10).\n"
                            "Leia pedido_tamanho(T) e use pegar_casquinha(T).",
                   exemplo="+!montar : pedido_tamanho(T) & pedido_sabor(S) <- pegar_casquinha(T); adicionar_sorvete(S); entregar."),
    "tipo_chocolate": No("Sorvete de chocolate", 90, ["variaveis"], "adicionar_sorvete(chocolate)", 2, 0,
                         novidade="A máquina agora faz CHOCOLATE (+$2). Cada cliente pede creme OU chocolate:\n"
                                  "pergunte (perguntar_pedido) e leia pedido_sabor(S)."),
    "tipo_misto": No("Sorvete misto", 200, ["tipo_chocolate"], "adicionar_sorvete(misto)", 3, 0,
                     novidade="A máquina agora faz MISTO (+$3)."),
    "bolacha": No("Massa de bolacha", 120, ["massas", "variaveis"], "adicionar_massa(bolacha)", 2, 2,
                  novidade="Nova massa: bolacha (+$2). Leia pedido_massa(M)."),
    "castanha": No("Massa de castanha", 200, ["bolacha"], "adicionar_massa(castanha)", 3, 2,
                   novidade="Nova massa: castanha (+$3)."),
    "caramelo": No("Calda de caramelo", 160, ["caldas", "variaveis"], "adicionar_calda(caramelo)", 4, 3,
                   novidade="Nova calda: caramelo (+$2)."),
    "menta": No("Calda de menta", 240, ["caramelo"], "adicionar_calda(menta)", 5, 3,
                novidade="Nova calda: menta (+$3)."),
    "cereja": No("Cereja", 200, ["coberturas"], "adicionar_cobertura(cereja)", 5, 4,
                 novidade="Nova cobertura: cereja (+$2)."),
    "mel": No("Mel", 260, ["cereja"], "adicionar_cobertura(mel)", 6, 4, novidade="Nova cobertura: mel (+$3)."),
    "granulado": No("Granulado", 320, ["mel"], "adicionar_cobertura(granulado)", 7, 4,
                    novidade="Nova cobertura: granulado (+$4)."),
    # --- fábrica --------------------------------------------------------------------------------------
    "robos": No("Mais robôs", 100, ["sentidos"], "mais um robô (e mais clientes)", 2, 5, niveis=5, mult=1.6,
                novidade="Um robô novo! Mais robôs também atraem mais clientes.\n"
                         "Ele segue a janela 'Todos os robôs', ou crie uma janela só para ele.\n"
                         "passar_pedido(robo2) passa o pedido que um robô perguntou para outro."),
    "bancadas": No("Bancadas", 90, ["robos"], "deixar(bancada1) / pegar_de(bancada1)", 3, 5, niveis=3,
                   mult=1.8, novidade="Uma bancada para os robôs passarem o sorvete um para o outro:\n"
                                      "deixar(bancada1) e pegar_de(bancada1). Percepções na_bancada(B), bancada_livre(B)."),
    "velocidade": No("Rodas rápidas", 40, [], "robôs andam e trabalham +30%", 0, 6, niveis=5, mult=1.7,
                     novidade="Seus robôs ficaram mais rápidos!"),
    "manutencao": No("Manutenção", 60, [], "menos falhas (-40%)", 1, 6, niveis=4, mult=1.8,
                     novidade="As máquinas falham menos agora."),
    "marketing": No("Marketing", 150, ["massas"], "mais clientes, pedidos +25%", 3, 6, niveis=4, mult=2.0,
                    novidade="Mais clientes, e cada sorvete vale mais!"),
    "franquia": No("Franquia", 2000, ["gerencia", "coberturas"], "abra sua franquia: FIM DE JOGO", 7, 6,
                   novidade="Você abriu a franquia! Obrigado por jogar."),
}


def custo(chave, nivel_atual):
    no = ARVORE[chave]
    return int(round(no.custo * no.mult ** nivel_atual))


# --- o que cada parte da linguagem exige ------------------------------------------------------
# Os comandos das estações (adicionar_massa, bater...) podem ser escritos antes de comprar a estação:
# assim dá para deixar o programa pronto. Sem a estação, o robô falha com nao_comprado.
ACOES_BASE = {"pegar_casquinha", "devolver", "jogar_fora", "adicionar_sorvete", "entregar", "perguntar_pedido",
              "dancar", "imprimir", "adicionar_massa", "bater", "adicionar_calda", "adicionar_cobertura"}
ACOES_DESBLOQUEIO = {"deixar": "bancadas", "pegar_de": "bancadas", "passar_pedido": "robos",
                     "esperar": "relogio", "temporizador": "relogio", "avisar": "comunicacao",
                     "comprar": "gerencia"}
EVENTOS_LIVRES = {"ligado", "terminou"}
EVENTOS_DESBLOQUEIO = {"recado": "comunicacao", "dinheiro": "gerencia", "preco": "gerencia", "robos": "gerencia",
                       "clientes": "gerencia"}
PERCEPCOES_GERENTE = {"dinheiro", "preco", "robos", "clientes"}


def verificar(prog: A.Programa, tem, percepcoes: set) -> list:
    """Devolve diagnósticos para os recursos bloqueados. ``tem(chave)`` diz se já foi comprado."""
    erros = []

    def bloq(oque, chave, pos):
        if not tem(chave):
            erros.append(Diagnostico("semantico", f"{oque}: ainda bloqueado. Compre '{ARVORE[chave].titulo}' "
                                                  f"na Árvore (T)", pos))

    def expr(no):
        if isinstance(no, A.Variavel):
            bloq(f"a variável '{no.nome}'", "variaveis", no.pos)
        elif isinstance(no, A.BinOp):
            bloq(f"a conta '{no.op}'", "operadores", no.pos)
            expr(no.esq)
            expr(no.dir)
        elif isinstance(no, A.Negativo):
            bloq("o sinal '-'", "operadores", no.pos)
            expr(no.expr)

    def literal(lit):
        for a in lit.args:
            expr(a)

    for ag in prog.agentes:
        if not ag.eh_modelo:
            bloq("a janela do gerente", "gerencia", ag.pos)
        for c in ag.crencas:
            bloq(f"a crença '{c.nome}.'", "memoria", c.pos)
            literal(c)
        for p in ag.planos:
            ev = p.evento.literal
            pos_ev = ev.pos or p.pos
            if not p.evento.objetivo:
                if p.evento.op == "-" and ev.nome not in EVENTOS_LIVRES:
                    bloq(f"o evento '-{ev.nome}'", "memoria", pos_ev)
                if ev.nome in EVENTOS_LIVRES:
                    pass
                elif ev.nome in EVENTOS_DESBLOQUEIO:
                    bloq(f"o evento +{ev.nome}", EVENTOS_DESBLOQUEIO[ev.nome], pos_ev)
                elif ev.nome in percepcoes:
                    bloq(f"o evento +{ev.nome}", "sentidos", pos_ev)
                else:
                    bloq(f"o evento +{ev.nome} (crença própria)", "memoria", pos_ev)
            literal(ev)
            if p.contexto:
                bloq("a condição ':'", "sentidos", p.contexto[0].pos or p.pos)
            for c in p.contexto:
                if isinstance(c, A.CondLiteral):
                    if c.negado:
                        bloq("'nao'", "operadores", c.pos or c.literal.pos)
                    if c.literal.nome in PERCEPCOES_GERENTE:
                        bloq(f"a percepção '{c.literal.nome}'", "gerencia", c.literal.pos)
                    elif c.literal.nome not in percepcoes:
                        bloq(f"a crença '{c.literal.nome}'", "memoria", c.literal.pos)
                    literal(c.literal)
                elif isinstance(c, A.Comparacao):
                    bloq(f"a comparação '{c.op}'", "operadores", c.pos)
                    expr(c.esq)
                    expr(c.dir)
            for a in p.acoes:
                if isinstance(a, A.AcaoCrenca):
                    bloq(f"'{a.op}{a.literal.nome}'", "memoria", a.pos or a.literal.pos)
                    literal(a.literal)
                elif isinstance(a, A.AcaoObjetivo):
                    literal(a.literal)
                else:
                    if a.nome in ACOES_DESBLOQUEIO:
                        bloq(f"o comando {a.nome}", ACOES_DESBLOQUEIO[a.nome], a.pos)
                    elif a.nome not in ACOES_BASE:
                        continue          # o compilador avisa "comando desconhecido" com sugestão
                    for x in a.args:
                        expr(x)
    return erros


# --- referência de comandos (tela F1) ------------------------------------------------------------------
# (seção, sintaxe, explicação, desbloqueio ou None)
COMANDOS = [
    ("Sintaxe", "+!produzir <- cmd1; cmd2.", "um OBJETIVO: o plano diz como fazê-lo, comando por comando", None),
    ("Sintaxe", "Executar (triângulo verde)", "o robô começa pelo PRIMEIRO objetivo da janela", None),
    ("Sintaxe", "!produzir", "no corpo de um plano: persegue o objetivo (o mesmo = repetir)", None),
    ("Sintaxe", "-!produzir <- ...", "o que fazer se o objetivo FALHAR (ex.: tentar de novo)", None),
    ("Sintaxe", "// comentário", "o robô ignora o resto da linha", None),
    ("Sintaxe", "+!x : condição <- ...", "só faz se a condição for verdadeira", "sentidos"),
    ("Sintaxe", "+evento <- ...", "reage a um evento: +novo_pedido, +falhou(M)...", "sentidos"),
    ("Sintaxe", "cond1 & cond2", "as duas ao mesmo tempo", "sentidos"),
    ("Sintaxe", "pedido_sabor(S)", "VARIÁVEIS (maiúscula) recebem valores", "variaveis"),
    ("Sintaxe", "nao c    X == Y    N > 2", "negação, comparações e contas", "operadores"),
    ("Sintaxe", "feitos(0).   -+feitos(N + 1)", "crenças próprias", "memoria"),
    ("Comandos", "perguntar_pedido", "balcão: pergunta ao cliente o que ele quer (espera se não tiver)", None),
    ("Comandos", "pegar_casquinha", "armazém: pega uma casquinha média (pode QUEBRAR)", None),
    ("Comandos", "pegar_casquinha(grande)", "escolhe o tamanho", "tamanhos"),
    ("Comandos", "devolver / jogar_fora", "devolve a casquinha vazia / joga fora o que tem na mão", None),
    ("Comandos", "adicionar_sorvete(creme)", "máquina: põe o sorvete (pode DERRAMAR)", None),
    ("Comandos", "entregar", "balcão: entrega a quem pediu (só se perguntou antes)", None),
    ("Comandos", "dancar   imprimir(\"oi\", X)", "dá uma voltinha / escreve na janela Saída", None),
    ("Comandos", "passar_pedido(robo2)", "passa o pedido que sabe para outro robô", "robos"),
    ("Comandos", "adicionar_massa(morango)", "massas: antes de bater (pode CAIR)", "massas"),
    ("Comandos", "bater(pouco | medio | bem)", "batedeira (pode PASSAR DO PONTO)", "batedeira"),
    ("Comandos", "adicionar_calda(chocolate)", "caldas (pode ENTUPIR)", "caldas"),
    ("Comandos", "adicionar_cobertura(chantilly)", "coberturas, até 2 (pode ESCORREGAR)", "coberturas"),
    ("Comandos", "deixar(bancada1) / pegar_de(bancada1)", "passa o sorvete para outro robô", "bancadas"),
    ("Comandos", "esperar(seg)  temporizador(seg, c)", "para um pouco / cria +c depois", "relogio"),
    ("Comandos", "avisar(robo2, recado)", "o robo2 percebe +recado(recado)", "comunicacao"),
    ("Comandos", "comprar(item)", "só o gerente: compra da árvore", "gerencia"),
    ("Opções", "pequeno  medio  grande", "tamanhos (P e G na árvore)", None),
    ("Opções", "creme  chocolate  misto", "tipos de sorvete", None),
    ("Opções", "morango  bolacha  castanha", "massas", "massas"),
    ("Opções", "chocolate  caramelo  menta", "caldas", "caldas"),
    ("Opções", "chantilly  cereja  mel  granulado", "coberturas", "coberturas"),
    ("Percepções", "tem_pedido   +novo_pedido", "sabe um pedido / acabou de saber de um", "sentidos"),
    ("Percepções", "pedido_sabor(S)  pedido_tamanho(T)", "o que o cliente pediu", "sentidos"),
    ("Percepções", "pedido_massa(M) pedido_ponto(P)", "", "sentidos"),
    ("Percepções", "pedido_calda(C) pedido_cobertura(C)", "", "sentidos"),
    ("Percepções", "livre   segurando(T)   estragado", "mãos vazias / casquinha / sorvete estragou", "sentidos"),
    ("Percepções", "tem_sorvete(S) tem_massa(M) batido(P)", "o que já tem no sorvete da mão", "sentidos"),
    ("Percepções", "tem_calda(C)   tem_cobertura(C)", "", "sentidos"),
    ("Percepções", "fila(N)   esta_em(L)", "clientes esperando ser atendidos / onde o robô está", "sentidos"),
    ("Percepções", "+falhou(M)   +entregou(V)", "eventos: falhou / recebeu $V", "sentidos"),
    ("Percepções", "na_bancada(B)  bancada_livre(B)", "", "bancadas"),
    ("Percepções", "+recado(X)", "outro robô avisou", "comunicacao"),
    ("Percepções", "dinheiro(D) preco(I, P) robos(N)", "só o gerente", "gerencia"),
    ("Falhas", "quebrou derramou caiu passou_do_ponto", "azar nas estações (Manutenção diminui)", None),
    ("Falhas", "entupiu escorregou recusado", "", None),
    ("Falhas", "sem_pedido cliente_foi_embora", "entregou sem perguntar / o cliente cansou", None),
    ("Falhas", "maos_cheias maos_vazias sem_casquinha", "erros de ordem: o robô não pôde fazer", None),
    ("Falhas", "sem_sorvete ja_tem ja_batido estragado", "", None),
    ("Atalhos do editor", "Ctrl+Enter  /  Ctrl+S", "executa a janela", None),
    ("Atalhos do editor", "Ctrl+A   Ctrl+L   Ctrl+D", "seleciona tudo / a linha / a palavra (de novo: próxima)", None),
    ("Atalhos do editor", "Shift+setas  Ctrl+Shift+setas", "seleciona letra a letra / palavra a palavra", None),
    ("Atalhos do editor", "Shift+Home/End  Ctrl+Home/End", "seleciona até o começo/fim / vai ao início/fim", None),
    ("Atalhos do editor", "mouse: arrastar, Shift+clique", "seleciona; 2 cliques = palavra, 3 = linha", None),
    ("Atalhos do editor", "Ctrl+C  Ctrl+X  Ctrl+V", "copia/recorta/cola (sem seleção: a linha toda)", None),
    ("Atalhos do editor", "Ctrl+Z  Ctrl+Y  Ctrl+Shift+Z", "desfaz / refaz", None),
    ("Atalhos do editor", "Ctrl+setas  Ctrl+Backspace/Del", "pula / apaga uma palavra", None),
    ("Atalhos do editor", "Alt+setas  Shift+Alt+setas", "move / duplica a linha", None),
    ("Atalhos do editor", "Ctrl+Shift+K   Ctrl+/ (ou Ctrl+;)", "apaga a linha / comenta", None),
    ("Atalhos do editor", "Tab  Shift+Tab", "indenta / desindenta a seleção", None),
    ("Atalhos do editor", "Ctrl+F  Enter  Shift+Enter", "procura / próxima / anterior", None),
    ("Atalhos do editor", "Ctrl+Espaço   Tab/Enter", "abre / aceita o autocompletar", None),
    ("Erros comuns", "esqueceu o '.' no fim do plano", "todo plano termina com ponto final", None),
    ("Erros comuns", "usou ',' entre comandos", "comandos são separados por ';'", None),
    ("Erros comuns", "esqueceu o '<-'", "+evento <- comandos.", None),
    ("Erros comuns", "Creme em vez de creme", "maiúscula é VARIÁVEL; opções são minúsculas", None),
    ("Erros comuns", "pegar_casqinha", "nome errado: o jogo sugere o certo", None),
    ("Erros comuns", "!produzir sem +!produzir", "todo objetivo precisa de um plano", None),
]
