"""Tutorial e missões: aparecem na janela de Informação e avançam sozinhos quando o objetivo é cumprido.

O tutorial principal vai devagar, um conceito por vez: começa com a fábrica vazia (só o armazém), depois
chega a máquina de sorvete e só então o balcão com os clientes. Depois dele, cada compra importante da
Árvore abre uma MISSÃO que ensina a usar a novidade: escolher o sabor pelo pedido, dois robôs com
programas diferentes, passar o pedido de um robô para o outro, linha de produção na bancada...
"""
from agentdsl import ast as A
from engine2d import Componente


def passo(titulo, texto, codigo="", botao=None, cond=None, ao_entrar=None, esperar_terminar=True):
    """``esperar_terminar``: só avança quando os robôs terminam o programa (assim o próximo passo começa
    de um jeito previsível). Nos passos que repetem para sempre, avança na hora."""
    return {"titulo": titulo, "texto": texto, "codigo": codigo, "botao": botao, "cond": cond, "ao_entrar": ao_entrar,
            "esperar": esperar_terminar}


PRODUZIR = ("+!produzir_sorvete <- perguntar_pedido; pegar_casquinha;\n"
            "    adicionar_sorvete(creme); entregar; !produzir_sorvete.\n"
            "-!produzir_sorvete <- jogar_fora; !produzir_sorvete.")

PASSOS = [
    # Cada passo começa EXATAMENTE onde o anterior terminou: Executar não "limpa" o robô. Se ele ficou com
    # uma casquinha na mão, ela continua lá (e o próximo programa precisa lidar com isso).
    passo("Bem-vindo à sua fábrica!",
          "Ela ainda está vazia: só tem o ARMAZÉM de casquinhas e um robô no meio.\n"
          "Você não controla o robô direto: você escreve o PROGRAMA dele na janela de código e aperta o "
          "triângulo verde para executar.\n"
          "Esta janela de Informação vai explicando tudo aos poucos. Arraste as janelas pela barra de cima e "
          "mude o tamanho puxando as bordas. Esc abre o menu.", botao="Próximo"),
    passo("1. Executar",
          "Na janela de código está escrito:  +!comecar <- dancar.\n"
          "+!comecar é um OBJETIVO: uma tarefa com nome. Depois do '<-' vêm os comandos dela.\n"
          "Quando você aperta Executar, o robô começa pelo PRIMEIRO objetivo da janela. Aperte e veja.",
          "+!comecar <- dancar.", cond=lambda t: t.viu_danca),
    passo("2. Pegar",
          "Troque dancar por pegar_casquinha e execute. O robô vai SOZINHO até o armazém e pega uma casquinha.\n"
          "Dica: digite \"peg\" e use o autocompletar (Tab ou Enter).",
          "+!comecar <- pegar_casquinha.", cond=lambda t: t.segurando()),
    passo("3. Só cabe uma",
          "O robô terminou o programa, mas a casquinha CONTINUA na mão dele: o que ele fez fica feito.\n"
          "Execute o mesmo programa de novo e veja o que acontece quando ele tenta pegar outra.",
          "+!comecar <- pegar_casquinha.",
          cond=lambda t: t.falhou_por("maos_cheias"), ao_entrar=lambda t: t.abrir_saida()),
    passo("4. Devolver",
          "Falhou: maos_cheias (veja o X vermelho e a janela Saída). Ele só segura uma coisa por vez.\n"
          "Antes de pegar outra, ele precisa DEVOLVER a que está segurando:",
          "+!comecar <- devolver.", cond=lambda t: t.fab.devolvidas > t.marco["devolvidas"]),
    passo("5. Um comando depois do outro",
          "Agora as mãos estão vazias. Para fazer duas coisas, separe os comandos com ';'.\n"
          "Pegue e devolva no mesmo programa: assim ele termina de mãos vazias de novo.",
          "+!comecar <- pegar_casquinha; devolver.", cond=lambda t: t.fab.devolvidas > t.marco["devolvidas"]),
    passo("6. A ordem importa",
          "E se devolver vier antes de pegar? Com as mãos vazias ele não tem o que devolver e FALHA "
          "(maos_vazias). Quando um comando falha, os seguintes nem acontecem. Experimente:",
          "+!comecar <- devolver; pegar_casquinha.", cond=lambda t: t.falhou_por("maos_vazias")),
    passo("7. Mais comandos no meio",
          "Como falhou logo no começo, ele continua de mãos vazias. Pode colocar quantos comandos quiser: "
          "pegue, dê uma dançadinha segurando a casquinha e devolva.",
          "+!comecar <- pegar_casquinha; dancar; devolver.", cond=lambda t: t.dancou_segurando),
    passo("8. Às vezes dá errado",
          "Nas fábricas as coisas falham sozinhas: a casquinha pode QUEBRAR. Execute o programa de pegar e "
          "devolver mais uma vez.",
          "+!comecar <- pegar_casquinha; devolver.", cond=lambda t: t.fab.falhas > t.marco["falhas"],
          ao_entrar=lambda t: t.quebrar_proxima()),
    passo("9. Um objetivo chama outro",
          "Quebrou, e ele parou de mãos vazias. !pegar no meio de um plano quer dizer: \"agora faça o "
          "objetivo pegar\". Assim dá para dividir o programa em partes com nome:",
          "+!comecar <- !pegar; devolver.\n+!pegar <- pegar_casquinha.",
          cond=lambda t: t.fab.devolvidas > t.marco["devolvidas"]),
    passo("10. Se falhar, tente de novo",
          "-!pegar diz o que fazer quando o objetivo pegar FALHA. Aqui: tentar de novo.\n"
          "Execute: a primeira casquinha vai quebrar, o robô tenta outra sozinho e depois devolve.",
          "+!comecar <- !pegar; devolver.\n+!pegar <- pegar_casquinha.\n-!pegar <- !pegar.",
          cond=lambda t: t.fab.falhas > t.marco["falhas"] and t.fab.devolvidas > t.marco["devolvidas"],
          ao_entrar=lambda t: t.quebrar_proxima()),
    passo("11. Repetir",
          "Um objetivo pode chamar a si mesmo no fim: assim ele repete para sempre.\n"
          "Faça o robô treinar pegando e devolvendo sem parar (o quadrado vermelho para).",
          "+!comecar <- pegar_casquinha; devolver; !comecar.",
          cond=lambda t: t.fab.devolvidas >= t.marco["devolvidas"] + 3, esperar_terminar=False),
    passo("12. Chegou a máquina de sorvete!",
          "A MÁQUINA DE SORVETE foi instalada. adicionar_sorvete(creme) põe sorvete na casquinha.\n"
          "Cuidado: o robô estava no meio do treino e pode ter ficado com uma casquinha na mão. "
          "jogar_fora no começo resolve: joga fora o que tiver (e, se não tiver nada, não faz nada).",
          "+!comecar <- jogar_fora; pegar_casquinha; adicionar_sorvete(creme).",
          cond=lambda t: t.montou_sorvete(), ao_entrar=lambda t: t.fab.liberar_estacao("maquina")),
    passo("13. Ainda sem clientes",
          "Ele está segurando o sorvete que você montou. A fábrica ainda não abriu: ninguém vai comprar. "
          "Jogue esse fora, monte outro e jogue fora também:",
          "+!comecar <- jogar_fora; pegar_casquinha; adicionar_sorvete(creme); jogar_fora.",
          cond=lambda t: t.fab.jogados >= t.marco["jogados"] + 2),
    passo("14. Abrimos! Pergunte antes",
          "O BALCÃO abriu e chegou o primeiro cliente. ANTES de fazer o sorvete, pergunte o que ele quer: "
          "perguntar_pedido (o robô vai ao balcão e anota). O pedido aparece no balão do cliente.\n"
          "Sem perguntar, entregar falha: ninguém pediu aquele sorvete!",
          "+!comecar <- perguntar_pedido; pegar_casquinha; adicionar_sorvete(creme); entregar.",
          cond=lambda t: t.fab.vendidos >= 1, ao_entrar=lambda t: t.fab.liberar_estacao("balcao")),
    passo("15. A fábrica funcionando",
          "Junte tudo: um objetivo que pergunta, monta, entrega e repete. Agora as falhas por azar também "
          "acontecem: se algo falhar, ele joga fora e recomeça (sem perguntar de novo: ele lembra o pedido).",
          PRODUZIR, cond=lambda t: t.fab.vendidos >= t.marco["vendidos"] + 3, esperar_terminar=False),
    passo("16. A Árvore",
          "Com o dinheiro você compra melhorias na Árvore (botão no alto ou tecla T): estações novas, partes da "
          "linguagem, robôs... Junte $30 e compre SENTIDOS (o robô passa a perceber o mundo).",
          cond=lambda t: t.fab.tem("sentidos"), esperar_terminar=False),
    passo("Pronto, a fábrica é sua!",
          "A cada compra importante aparece aqui uma MISSÃO explicando a novidade (sabores, robôs, estações...). "
          "A primeira é a dos Sentidos, logo depois deste aviso.\n"
          "F1 mostra todos os comandos e os erros comuns. Meta: abrir a FRANQUIA.", botao="Entendi!"),
]
# até este passo do tutorial, nada falha por azar (só o que o tutorial quebra de propósito)
PASSO_SEM_AZAR = next(i for i, p in enumerate(PASSOS) if p["titulo"].startswith("15."))


# --- o que procurar no programa que está rodando (para as missões de linguagem) -----------------------
def _condicao_com_variavel(p):
    return any(isinstance(c, A.CondLiteral) and any(isinstance(a, A.Variavel) for a in c.literal.args)
               for c in p.contexto)


def _condicao_negada_ou_comparacao(p):
    return any(isinstance(c, A.Comparacao) or (isinstance(c, A.CondLiteral) and c.negado) for c in p.contexto)


def _muda_crenca(p):
    return any(isinstance(a, A.AcaoCrenca) for a in p.acoes)


def _usa_relogio(p):
    return any(getattr(a, "nome", None) in ("esperar", "temporizador") for a in p.acoes)


def _codigo_massa(t):
    if t.fab.tem("variaveis"):
        return ("+!montar : pedido_sabor(S) & pedido_massa(M) <- pegar_casquinha;\n"
                "    adicionar_sorvete(S); adicionar_massa(M); entregar; !produzir.")
    return ("+!produzir_sorvete <- perguntar_pedido; pegar_casquinha; adicionar_sorvete(creme);\n"
            "    adicionar_massa(morango); entregar; !produzir_sorvete.")


MISSOES = {
    "sentidos": [
        passo("Missão: condições",
              "Agora um plano pode ter CONDIÇÃO, depois do ':'. Com vários planos de mesmo nome, o robô testa "
              "de cima para baixo e usa o PRIMEIRO cuja condição é verdadeira.\n"
              "'livre' é verdadeiro quando ele está de mãos vazias. Assim ele só joga fora quando tem algo na "
              "mão (quando você aperta Executar no meio do serviço, por exemplo). Venda um sorvete assim:",
              "+!produzir : livre <- perguntar_pedido; !montar.\n"
              "+!produzir <- jogar_fora; !produzir.\n"
              "+!montar <- pegar_casquinha; adicionar_sorvete(creme); entregar; !produzir.\n"
              "-!montar <- jogar_fora; !montar.",
              cond=lambda t: t.fab.vendidos > t.marco["vendidos"] and t.programa_usa(lambda p: p.contexto)),
        passo("O que o robô percebe",
              "Outras percepções para usar nas condições: tem_pedido (já sabe o que o cliente quer), estragado "
              "(o sorvete da mão estragou), segurando(...), tem_sorvete(...), fila(...).\n"
              "Também dá para REAGIR a eventos: um plano +novo_pedido <- ... roda quando o robô fica sabendo "
              "de um pedido (útil com vários robôs). F1 lista tudo.\n"
              "Próximo passo sugerido: VARIÁVEIS, para o robô ler o que o cliente pediu.", botao="Entendi"),
    ],
    "variaveis": [
        passo("Missão: variáveis",
              "Um nome com MAIÚSCULA é uma VARIÁVEL: ela recebe o valor que o robô percebe. Depois de "
              "perguntar_pedido, pedido_sabor(S) faz S valer o sabor pedido, e adicionar_sorvete(S) usa esse "
              "valor.\n"
              "Hoje todo cliente pede creme, mas com o programa lendo o pedido, quando você comprar CHOCOLATE "
              "ou TAMANHOS ele já acerta sozinho. Venda um sorvete lendo o pedido:",
              "+!produzir : livre <- perguntar_pedido; !montar.\n"
              "+!produzir <- jogar_fora; !produzir.\n"
              "+!montar : pedido_sabor(S) <- pegar_casquinha; adicionar_sorvete(S); entregar; !produzir.\n"
              "-!montar <- jogar_fora; !montar.",
              cond=lambda t: t.fab.vendidos > t.marco["vendidos"] and t.programa_usa(_condicao_com_variavel)),
    ],
    "operadores": [
        passo("Missão: nao e comparações",
              "'nao' inverte uma condição: nao livre = está segurando algo. Assim dá para escrever o caso "
              "'tem algo na mão' primeiro, sem depender da ordem dos planos.\n"
              "Com Variáveis também vale comparar e fazer contas: fila(N) & N > 2, D >= P + 100...\n"
              "Venda um sorvete com um plano que use 'nao' ou uma comparação:",
              "+!produzir : nao livre <- jogar_fora; !produzir.\n"
              "+!produzir <- perguntar_pedido; !montar.\n"
              "+!montar <- pegar_casquinha; adicionar_sorvete(creme); entregar; !produzir.\n"
              "-!montar <- jogar_fora; !montar.",
              cond=lambda t: t.fab.vendidos > t.marco["vendidos"] and t.programa_usa(_condicao_negada_ou_comparacao)),
    ],
    "memoria": [
        passo("Missão: memória",
              "O robô pode LEMBRAR coisas: crenças próprias. 'abrindo.' sozinho numa linha é uma crença inicial; "
              "-abrindo no corpo apaga, +abrindo cria.\n"
              "Aqui ele dança só na primeira vez (para abrir a loja) e depois esquece que estava abrindo. "
              "Venda um sorvete assim:",
              "abrindo.\n"
              "+!produzir : abrindo <- dancar; -abrindo; !produzir.\n"
              "+!produzir : livre <- perguntar_pedido; !montar.\n"
              "+!produzir <- jogar_fora; !produzir.\n"
              "+!montar <- pegar_casquinha; adicionar_sorvete(creme); entregar; !produzir.\n"
              "-!montar <- jogar_fora; !montar.",
              cond=lambda t: t.fab.vendidos > t.marco["vendidos"] and t.programa_usa(_muda_crenca)),
        passo("Contando com a memória",
              "Com Variáveis e Operadores a memória vira um contador:\n"
              "feitos(0).   +entregou(_V) : feitos(N) <- -+feitos(N + 1).\n"
              "-+ troca a crença antiga pela nova. Cada crença nova também gera um evento (+feitos(...)).",
              botao="Entendi"),
    ],
    "relogio": [
        passo("Missão: esperar",
              "esperar(1) para o robô por 1 segundo. Útil para não ficar tentando de novo sem parar quando "
              "algo falha. Venda um sorvete com um esperar no programa:",
              "+!produzir : livre <- perguntar_pedido; !montar.\n"
              "+!produzir <- jogar_fora; !produzir.\n"
              "+!montar <- pegar_casquinha; adicionar_sorvete(creme); entregar; !produzir.\n"
              "-!montar <- jogar_fora; esperar(1); !montar.",
              cond=lambda t: t.fab.vendidos > t.marco["vendidos"] and t.programa_usa(_usa_relogio)),
    ],
    "tipo_chocolate": [
        passo("Missão: qual sabor?",
              "Agora cada cliente pede CREME ou CHOCOLATE. Depois de perguntar_pedido o robô sabe o sabor: a "
              "percepção pedido_sabor(S). S é uma VARIÁVEL: ela recebe creme ou chocolate, e "
              "adicionar_sorvete(S) usa esse valor. Venda um sorvete de chocolate:",
              "+!produzir <- perguntar_pedido; !montar.\n"
              "+!montar : pedido_sabor(S) <- pegar_casquinha; adicionar_sorvete(S); entregar; !produzir.\n"
              "-!montar <- jogar_fora; !montar.\n-!produzir <- !produzir.",
              cond=lambda t: t.fab.vendas_tipo.get("chocolate", 0) > t.marco["chocolate"]),
        passo("Sabor certo!",
              "Se o robô fizesse sempre creme, quem pediu chocolate pagaria menos (ou recusaria).\n"
              "A informação do pedido também pode ir para outro robô: com mais robôs, passar_pedido(robo2) "
              "entrega o pedido (e o sabor) para o robo2 fazer.", botao="Entendi"),
    ],
    "robos": [
        passo("Missão: dois robôs",
              "Chegou o robo2! Por enquanto ele segue a janela 'Todos os robôs', igual ao robo1.\n"
              "Para ele ter um programa só dele: clique em '+ Janela de código'. No alto da janela nova aparece "
              "o nome do robô que ela controla (clique no nome para trocar).",
              cond=lambda t: t.tem_janela("robo2")),
        passo("Missão: dividir o trabalho",
              "Um robô ATENDE: pergunta e passa o pedido com passar_pedido(robo2). O outro MONTA quando fica "
              "sabendo de um pedido: o evento +novo_pedido. Escreva cada parte na sua janela e execute as duas.",
              "// janela Todos os robôs (o robo1 atende)\n"
              "+!atender <- perguntar_pedido; passar_pedido(robo2); !atender.\n-!atender <- !atender.\n\n"
              "// janela do robo2 (monta)\n+!comecar <- dancar.\n+novo_pedido <- !montar.\n"
              "+!montar <- pegar_casquinha; adicionar_sorvete(creme); entregar.\n-!montar <- jogar_fora; !montar.",
              cond=lambda t: (t.fab.pedidos_passados > t.marco["passados"]
                              and t.fab.vendas_robo.get("robo2", 0) > t.marco["robo2"])),
        passo("Trabalho em equipe!",
              "Isso é um sistema MULTIAGENTE: cada robô é um agente com seu próprio programa, e eles trocam "
              "informação (o pedido). Com Bancadas, um pode até passar o sorvete pela metade para o outro "
              "terminar.", botao="Legal!"),
    ],
    "bancadas": [
        passo("Missão: linha de produção",
              "Com a bancada, um robô começa o sorvete e outro termina. O pedido vai junto com o sorvete!\n"
              "robo1: pergunta, monta e deixa na bancada1. robo2: pega da bancada e entrega.",
              "// janela Todos os robôs (robo1)\n"
              "+!base <- perguntar_pedido; pegar_casquinha; adicionar_sorvete(creme); deixar(bancada1); !base.\n"
              "-!base <- jogar_fora; !base.\n\n// janela do robo2\n"
              "+!finalizar : na_bancada(bancada1) <- pegar_de(bancada1); entregar; !finalizar.\n"
              "+!finalizar <- dancar; !finalizar.\n-!finalizar <- jogar_fora; !finalizar.",
              cond=lambda t: t.fab.pegas_bancada > t.marco["bancada"]),
    ],
    "comunicacao": [
        passo("Missão: avisar",
              "avisar(robo2, pronto) faz o robo2 perceber o evento +recado(pronto). Em vez de ficar conferindo a "
              "bancada, o robo2 espera o aviso:",
              "// robo1: ...; deixar(bancada1); avisar(robo2, pronto); !base.\n"
              "// robo2:\n+!comecar <- dancar.\n+recado(pronto) <- pegar_de(bancada1); entregar.",
              cond=lambda t: t.fab.recados > t.marco["recados"]),
    ],
    "massas": [
        passo("Missão: a massa",
              "Os pedidos agora têm uma MASSA (morango). Adicione antes de entregar: quem recebe o sorvete "
              "completo paga mais (e dá gorjeta!).", _codigo_massa,
              cond=lambda t: t.fab.vendas_perfeitas > t.marco["perfeitas"]),
    ],
    "batedeira": [
        passo("Missão: o ponto",
              "Cada cliente pede o sorvete batido pouco, medio ou bem: leia pedido_ponto(P) e use bater(P) "
              "(precisa de Variáveis). Bater vem depois da massa.",
              "+!bater : pedido_ponto(P) <- bater(P).",
              cond=lambda t: t.fab.vendas_perfeitas > t.marco["perfeitas"]),
    ],
    "caldas": [
        passo("Missão: a calda",
              "Leia pedido_calda(C) e use adicionar_calda(C) depois de bater.",
              "+!calda : pedido_calda(C) <- adicionar_calda(C).",
              cond=lambda t: t.fab.vendas_perfeitas > t.marco["perfeitas"]),
    ],
    "coberturas": [
        passo("Missão: coberturas",
              "Cada cliente pede 1 ou 2 coberturas. Repita enquanto faltar alguma (precisa de Operadores):",
              "+!cobrir : pedido_cobertura(C) & nao tem_cobertura(C) <- adicionar_cobertura(C); !cobrir.\n"
              "+!cobrir <- entregar.",
              cond=lambda t: t.fab.vendas_perfeitas > t.marco["perfeitas"]),
    ],
    "tamanhos": [
        passo("Missão: tamanhos",
              "Agora o cliente escolhe pequeno, medio ou grande: leia pedido_tamanho(T) e use pegar_casquinha(T).",
              "+!montar : pedido_tamanho(T) & pedido_sabor(S) <- pegar_casquinha(T);\n"
              "    adicionar_sorvete(S); entregar; !produzir.",
              cond=lambda t: t.fab.vendas_perfeitas > t.marco["perfeitas"]),
    ],
    "gerencia": [
        passo("Missão: o gerente",
              "Crie uma janela de código e escolha 'Gerente' no alto dela. O gerente não monta sorvete: ele "
              "percebe o dinheiro e compra sozinho. Execute a janela dele.",
              "+dinheiro(D) : preco(manutencao, P) & D >= P <- comprar(manutencao).\n"
              "+dinheiro(D) : preco(robos, P) & D >= P + 100 <- comprar(robos).",
              cond=lambda t: t.fab.compras_gerente > t.marco["gerente"]),
    ],
}

GUIA = passo("Guia rápido",
             "Objetivo: +!nome <- comandos.   !nome persegue,   -!nome <- ... se falhar.\n"
             "Executar começa pelo primeiro objetivo da janela. F1 mostra comandos, atalhos e erros comuns. "
             "T abre a Árvore. Cada janela de código controla todos os robôs ou só um (clique no nome no alto).",
             PRODUZIR)


class Tutorial(Componente):
    def iniciar(self):
        self.cena.servicos["tutorial"] = self
        self.fab = self.cena.servicos["sorveteria"]
        salvo = self.fab.dados_salvos or {}
        self.passo = min(salvo.get("tutorial", 0), len(PASSOS))
        self.missoes = list(salvo.get("missoes", []))      # fila: [chave, passo]
        self.feitas = set(salvo.get("missoes_feitas", []))
        # jogos salvos antes de existir a missão: o que já foi comprado e nunca teve missão entra na fila
        for chave in MISSOES:
            if self.fab.tem(chave) and chave not in self.feitas and all(m[0] != chave for m in self.missoes):
                self.missoes.append([chave, 0])
        self._marcar()

    passo_sem_azar = PASSO_SEM_AZAR

    @property
    def total(self):
        return len(PASSOS)

    @property
    def ativo(self):
        return self.passo < len(PASSOS)

    def _marcar(self):
        f = self.fab
        self.marco = {"devolvidas": f.devolvidas, "falhas": f.falhas, "vendidos": f.vendidos,
                      "falhas_comando": f.falhas_comando, "jogados": f.jogados,
                      "chocolate": f.vendas_tipo.get("chocolate", 0), "passados": f.pedidos_passados,
                      "robo2": f.vendas_robo.get("robo2", 0), "bancada": f.pegas_bancada, "recados": f.recados,
                      "perfeitas": f.vendas_perfeitas, "gerente": f.compras_gerente,
                      "por_motivo": dict(f.contagem_falhas)}
        self.viu_danca = self.dancou_segurando = False

    def reiniciar(self):
        self.passo = 0
        self._marcar()

    def recomecar(self):
        self.reiniciar()
        self.missoes, self.feitas = [], set()

    def estado(self):
        return {"missoes": self.missoes, "missoes_feitas": sorted(self.feitas)}

    # --- missões ---------------------------------------------------------------------------------------
    def ao_comprar(self, chave):
        if chave in MISSOES and chave not in self.feitas and all(m[0] != chave for m in self.missoes):
            self.missoes.append([chave, 0])
            if len(self.missoes) == 1:
                self._marcar()

    def _atual(self):
        """O passo que está valendo agora: do tutorial, da missão da vez ou None."""
        if self.ativo:
            return PASSOS[self.passo]
        if self.missoes:
            chave, k = self.missoes[0]
            return MISSOES[chave][k]
        return None

    # --- ajudantes das condições -----------------------------------------------------------------
    def _robos(self):
        return [g.obter("Robo") for g in self.fab.robos() if g.obter("Robo")]

    def segurando(self):
        return any(r.item is not None for r in self._robos())

    def montou_sorvete(self):
        return any(r.item is not None and r.item["tipo"] for r in self._robos())

    def programa_usa(self, teste):
        """Algum plano que os robôs estão rodando passa no teste?"""
        for r in self._robos():
            ag = getattr(r.agente, "ag", None) if r.agente is not None else None
            for lista in (ag.planos.values() if ag is not None else ()):
                if any(teste(p) for p in lista):
                    return True
        return False

    def falhou_por(self, motivo):
        """Algum robô falhou com esse motivo desde que o passo começou?"""
        return self.fab.contagem_falhas.get(motivo, 0) > self.marco["por_motivo"].get(motivo, 0)

    def quebrar_proxima(self):
        self.fab.forcar_quebra = 1

    def abrir_saida(self):
        painel = self.cena.servicos.get("painel")
        if painel is not None:
            painel.mostrar_janela("saida")

    def tem_janela(self, robo):
        painel = self.cena.servicos.get("painel")
        return painel is not None and any(j.alvo == robo and not j.fechada for j in painel.codigos())

    # --- ciclo -----------------------------------------------------------------------------------------
    def atualizar(self, dt):
        for r in self._robos():
            if r.atual and r.atual[0] == "dancar":
                self.viu_danca = True
                if r.item is not None:
                    self.dancou_segurando = True
        atual = self._atual()
        if atual is not None and atual["cond"] is not None and atual["cond"](self):
            if self.ativo and atual["esperar"] and any(r.ocupado for r in self._robos()):
                return                      # cumpriu, mas espera o robô terminar o programa
            self.avancar()

    def avancar(self):
        if self.ativo:
            self.passo += 1
        elif self.missoes:
            chave, k = self.missoes[0]
            if k + 1 < len(MISSOES[chave]):
                self.missoes[0][1] = k + 1
            else:
                self.missoes.pop(0)
                self.feitas.add(chave)
        self._marcar()
        atual = self._atual()
        if atual is not None and atual["ao_entrar"]:
            atual["ao_entrar"](self)
        painel = self.cena.servicos.get("painel")
        if painel is not None:
            painel.mostrar_janela("info")
        self.fab.salvar_agora()

    def conteudo(self):
        """(título, texto, código, rótulo do botão | None) para a janela de Informação."""
        atual = self._atual() or GUIA
        codigo = atual["codigo"](self) if callable(atual["codigo"]) else atual["codigo"]
        botao = atual["botao"] if atual is not GUIA else None
        return atual["titulo"], atual["texto"], codigo, botao

    @property
    def em_missao(self):
        return not self.ativo and bool(self.missoes)
