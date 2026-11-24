"""O cardápio da sorveteria (como no Papa's Freezeria) e o "contrato" com a AgentDSL.

Um sorvete passa por etapas, cada uma numa estação:
  casquinha (tamanho) -> sorvete (tipo) -> massa -> bater (ponto) -> calda -> cobertura(s) -> entregar
Tudo o que está declarado com percepcao_dsl / alvo_dsl é conhecido pelo compilador da DSL.
"""
from agentdsl.interpretador import Simbolo
from engine2d.projeto import alvo_dsl, percepcao_dsl

TAMANHOS = ["pequeno", "medio", "grande"]
TIPOS = ["creme", "chocolate", "misto"]
MASSAS = ["morango", "bolacha", "castanha"]
PONTOS = ["pouco", "medio", "bem"]               # bater(pouco | medio | bem)
CALDAS = ["chocolate", "caramelo", "menta"]
COBERTURAS = ["chantilly", "cereja", "mel", "granulado"]

PRECO_TAMANHO = {"pequeno": 5, "medio": 7, "grande": 10}
PRECO_EXTRA = 3                                  # cada etapa extra do pedido (massa, ponto, calda, cobertura)
PRECO_OPCAO = {"chocolate": 2, "misto": 3, "bolacha": 2, "castanha": 3, "caramelo": 2, "menta": 3,
               "cereja": 2, "mel": 3, "granulado": 4}

S = "Assets/Sprites/Itens/"
ICONES = {
    "casquinha": S + "casquinha.png", "quebrada": S + "quebrada.png", "estragado": S + "estragado.png",
    "creme": S + "sorvete_creme.png", "chocolate": S + "sorvete_chocolate.png", "misto": S + "sorvete_misto.png",
    "morango": S + "morango.png", "bolacha": S + "bolacha.png", "castanha": S + "castanha.png",
    "calda_chocolate": S + "calda_chocolate.png", "calda_caramelo": S + "calda_caramelo.png",
    "calda_menta": S + "calda_menta.png",
    "chantilly": S + "chantilly.png", "cereja": S + "cereja.png", "mel": S + "mel.png",
    "granulado": S + "granulado.png",
}


def atomo(nome: str) -> Simbolo:
    return Simbolo(nome)


def texto(valor) -> str:
    return valor.nome if isinstance(valor, Simbolo) else str(valor)


def novo_item(tamanho, ticket=None):
    return {"tamanho": tamanho, "tipo": None, "massa": None, "ponto": None, "calda": None,
            "coberturas": [], "estragado": False, "ticket": ticket}


def icone_item(item):
    if item is None:
        return None
    if item["estragado"]:
        return ICONES["estragado"]
    return ICONES[item["tipo"]] if item["tipo"] else ICONES["casquinha"]


def descrever_item(item):
    if item is None:
        return "nada"
    if item["estragado"]:
        return "sorvete estragado"
    partes = [f"casquinha {item['tamanho']}"]
    if item["tipo"]:
        partes.append(item["tipo"])
    if item["massa"]:
        partes.append(f"+{item['massa']}")
    if item["ponto"]:
        partes.append(f"batido {item['ponto']}")
    if item["calda"]:
        partes.append(f"calda {item['calda']}")
    partes += item["coberturas"]
    return ", ".join(partes)


# --- eventos de controle -------------------------------------------------------------------
percepcao_dsl("ligado")                        # (instantâneo) você apertou Executar
percepcao_dsl("terminou")                      # (instantâneo) o robô acabou todos os comandos
percepcao_dsl("falhou", "atomo")               # (instantâneo) um comando falhou: falhou(quebrou)
percepcao_dsl("entregou", "num")               # (instantâneo) entregou um sorvete e recebeu $N
percepcao_dsl("novo_pedido")                   # (instantâneo) o robô ficou sabendo de um pedido
# --- o que o robô segura ---------------------------------------------------------------------
percepcao_dsl("livre")                         # mãos vazias
percepcao_dsl("segurando", "atomo")            # segurando(pequeno|medio|grande): uma casquinha
percepcao_dsl("tem_sorvete", "atomo")          # tem_sorvete(creme)
percepcao_dsl("tem_massa", "atomo")            # tem_massa(morango)
percepcao_dsl("batido", "atomo")               # batido(medio)
percepcao_dsl("tem_calda", "atomo")            # tem_calda(caramelo)
percepcao_dsl("tem_cobertura", "atomo")        # tem_cobertura(cereja)
percepcao_dsl("estragado")                     # o sorvete da mão estragou (jogue fora)
percepcao_dsl("esta_em", "atomo")              # esta_em(maquina)
# --- o pedido (do sorvete que segura, ou o anotado no balcão) --------------------------------------
percepcao_dsl("tem_pedido")                    # sabe qual pedido está fazendo
percepcao_dsl("pedido_tamanho", "atomo")       # pedido_tamanho(grande)
percepcao_dsl("pedido_sabor", "atomo")         # pedido_sabor(chocolate)
percepcao_dsl("pedido_massa", "atomo")
percepcao_dsl("pedido_ponto", "atomo")
percepcao_dsl("pedido_calda", "atomo")
percepcao_dsl("pedido_cobertura", "atomo")
# --- o mundo -------------------------------------------------------------------------------------------
percepcao_dsl("fila", "num")                   # quantos pedidos ninguém anotou ainda
percepcao_dsl("na_bancada", "atomo")           # na_bancada(bancada1): tem sorvete esperando ali
percepcao_dsl("bancada_livre", "atomo")
percepcao_dsl("recado", "atomo")               # recado(X): outro robô mandou avisar(eu, X)
# --- o gerente ---------------------------------------------------------------------------------------
percepcao_dsl("dinheiro", "num")
percepcao_dsl("preco", "atomo", "num")         # preco(robos, 120) ...
percepcao_dsl("robos", "num")
percepcao_dsl("clientes", "num")

PERCEPCOES_ROBO = {"ligado", "terminou", "falhou", "entregou", "livre", "segurando", "tem_sorvete", "tem_massa",
                   "batido", "tem_calda", "tem_cobertura", "estragado", "esta_em", "tem_pedido", "pedido_tamanho",
                   "pedido_sabor", "novo_pedido",
                   "pedido_massa", "pedido_ponto", "pedido_calda", "pedido_cobertura", "fila", "na_bancada",
                   "bancada_livre", "recado"}
PERCEPCOES_GERENTE = {"dinheiro", "preco", "robos", "clientes"}

ESTACOES = ["armazem", "maquina", "massas", "batedeira", "caldas", "coberturas", "balcao",
            "bancada1", "bancada2", "bancada3"]
MOTIVOS = ["quebrou", "derramou", "caiu", "passou_do_ponto", "entupiu", "escorregou", "maos_cheias",
           "maos_vazias", "sem_casquinha", "sem_sorvete", "ja_tem", "ja_batido", "estragado", "nao_comprado",
           "nao_existe", "sem_cliente", "recusado", "sem_pedido", "cliente_foi_embora", "nao_pode", "sem_dinheiro", "ocupada", "vazia",
           "sem_plano", "opcao_bloqueada", "opcao_invalida"]
ROBOS = [f"robo{i}" for i in range(1, 8)]
ITENS_ARVORE = ["sentidos", "variaveis", "operadores", "memoria", "relogio", "comunicacao", "gerencia",
                "massas", "batedeira", "caldas", "coberturas", "tamanhos", "tipo_chocolate", "tipo_misto",
                "bolacha", "castanha", "caramelo", "menta", "cereja", "mel", "granulado", "robos", "bancadas",
                "velocidade", "manutencao", "marketing", "franquia"]
alvo_dsl(*TAMANHOS, *TIPOS, *MASSAS, *PONTOS, *CALDAS, *COBERTURAS, *ESTACOES, *MOTIVOS, *ROBOS, *ITENS_ARVORE)
