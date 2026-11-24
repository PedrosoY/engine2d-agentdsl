"""Gera o ProjetoSorveteria: sprites (Kenney Tiny Factory + Food Expansion, CC0, e pixel art), prefab e cena.

Os scripts (Assets/Scripts) e o programa inicial (Assets/Agentes/fabrica.agt) já ficam na pasta;
este gerador só (re)cria as imagens, o prefab do robô, a cena, o projeto.json e o LEIA-ME.
    python gerar_sorveteria.py
"""
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw

from engine2d.projeto import Projeto

RAIZ = Path(__file__).parent
PROJ = RAIZ / "ProjetoSorveteria"
FAB = RAIZ / "assets/kenney_tiny_factory/Tiles"
COM = RAIZ / "assets/kenney_food/Tiles"
SPR = PROJ / "Assets/Sprites"


def tile(pasta, n):
    return Image.open(pasta / f"tile_{n:04d}.png").convert("RGBA")


def salvar(img, rel):
    caminho = SPR / rel
    caminho.parent.mkdir(parents=True, exist_ok=True)
    img.save(caminho)


def tingir(img, cor_clara, cor_escura):
    """Troca os tons claros e pouco saturados (o creme branco) por um degradê da cor dada."""
    out = img.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if a and max(r, g, b) - min(r, g, b) < 40 and max(r, g, b) > 110:
                t = (max(r, g, b) - 110) / 145
                px[x, y] = tuple(int(cor_escura[i] + (cor_clara[i] - cor_escura[i]) * t) for i in range(3)) + (a,)
    return out


def desenhar(grade, cores, tam=16):
    """Pixel art a partir de linhas de texto: cada caractere é uma cor da tabela (``.`` = transparente)."""
    img = Image.new("RGBA", (tam, tam), (0, 0, 0, 0))
    dy = (tam - len(grade)) // 2
    for y, linha in enumerate(grade):
        dx = (tam - len(linha)) // 2
        for x, c in enumerate(linha):
            if c != ".":
                img.putpixel((x + dx, y + dy), cores[c])
    return img


K = (40, 25, 35, 255)
CORES = {"k": K, "c": (214, 160, 90, 255), "C": (170, 110, 55, 255), "r": (220, 45, 60, 255),
         "w": (255, 220, 140, 255), "g": (70, 170, 70, 255), "b": (150, 90, 45, 255), "B": (110, 62, 30, 255),
         "y": (250, 200, 60, 255), "Y": (215, 150, 30, 255), "W": (255, 255, 255, 255), "s": (220, 220, 230, 255),
         "p": (255, 120, 180, 255), "u": (90, 160, 255, 255), "v": (120, 200, 90, 255), "x": (130, 140, 110, 255),
         "X": (95, 105, 80, 255)}
CASQUINHA = ["...kkkkkkkk...", "..kcCcCcCcCk..", "..kCcCcCcCck..", "...kcCcCcCk...", "...kCcCcCck...",
             "....kcCcCk....", "....kCcCck....", ".....kcCk.....", ".....kCck.....", "......kk......"]
QUEBRADA = ["..............", "..kkk....kkk..", ".kcCk...kCck..", ".kCck....kk...", "..kk..kk......",
            "......kCk.....", ".....kcCk..kk.", "......kk..kCk.", "...........k.."]
MORANGO = ["....g.g.g...", ".....ggg....", "...kgggggk..", "..krrrrrrrk.", ".krrwrrrwrrk", ".krrrrrrrrrk",
           ".krwrrrrwrrk", "..krrrwrrrk.", "..krrrrrrk..", "...krrwrk...", "....krrk....", ".....kk....."]
CASTANHA = ["....kkkk....", "..kkbbbbkk..", ".kbbBbbBbbk.", ".kbBbbbbBbk.", "kbbbbBbbbbbk", "kbBbbbbbBbbk",
            ".kbbbBbbbbk.", "..kkbbbbkk..", "....kkkk...."]
CEREJA = ["......g.....", ".....g......", "....g.......", "...g........", "..kkk.......", ".krrrk......",
          "krwrrrk.....", "krrrrrk.....", ".krrrk......", "..kkk......."]
MEL = ["....kk....", "...kyyk...", "..kyyyyk..", ".kyywyyyk.", ".kyyyyYyk.", ".kyyyYYyk.", "..kyYYYk..",
       "...kkkk..."]
GOTA = ["....kk....", "...kXXk...", "..kXXXXk..", ".kXXwXXXk.", ".kXXXXXXk.", ".kXXXXXXk.", "..kXXXXk..",
        "...kkkk..."]
GRANULADO = ["...........", "..r...u....", "......y..p.", ".p..g......", "....r...u..", ".y......g..",
             "...u..p....", "........r..", ".g..y......"]
ESTRAGADO = ["..............", "....kkkk......", "..kkxxxxkk....", ".kxxXxxxxxk...", "kxxxxxXxxxxk..",
             "kxXxxxxxxXxk..", ".kxxxxXxxxk...", "..kkxxxxkk....", "....kkkk......"]


def gota(cor):
    escura = tuple(int(c * 0.7) for c in cor[:3]) + (255,)
    return desenhar(GOTA, {**CORES, "X": cor, "w": (255, 255, 255, 255)} | {"Y": escura})


def sorvete(cor_clara, cor_escura, misto=False):
    """Casquinha com uma bola de sorvete por cima (o creme vem da Food Expansion, tingido)."""
    img = Image.new("RGBA", (18, 18), (0, 0, 0, 0))
    bola = tingir(tile(COM, 107), cor_clara, cor_escura)
    if misto:   # metade chocolate
        outra = tingir(tile(COM, 107), (170, 110, 70), (95, 55, 30))
        bola.paste(outra.crop((9, 0, 18, 18)), (9, 0))
    bola = bola.resize((14, 12), Image.NEAREST)
    cone = desenhar(CASQUINHA, CORES, 14).crop((0, 2, 14, 12))
    img.paste(cone, (2, 8), cone)
    img.paste(bola, (2, 0), bola)
    return img


def gerar_sprites():
    # estações (Tiny Factory)
    for nome, n in (("armazem", 85), ("maquina", 111), ("massas", 75), ("caldas", 126), ("coberturas", 99),
                    ("balcao", 100), ("bancada", 6)):
        salvar(tile(FAB, n), f"Estacoes/{nome}.png")
    salvar(tile(FAB, 87), "Estacoes/batedeira.png")
    salvar(tile(FAB, 88), "Estacoes/batedeira_b.png")
    salvar(tile(FAB, 89), "Estacoes/batedeira_c.png")
    salvar(tile(FAB, 128), "Personagens/robo.png")
    salvar(tile(FAB, 120), "Personagens/cliente.png")
    # itens
    salvar(desenhar(CASQUINHA, CORES), "Itens/casquinha.png")
    salvar(desenhar(QUEBRADA, CORES), "Itens/quebrada.png")
    salvar(desenhar(ESTRAGADO, CORES), "Itens/estragado.png")
    salvar(sorvete((255, 246, 214), (196, 170, 120)), "Itens/sorvete_creme.png")
    salvar(sorvete((170, 110, 70), (95, 55, 30)), "Itens/sorvete_chocolate.png")
    salvar(sorvete((255, 246, 214), (196, 170, 120), misto=True), "Itens/sorvete_misto.png")
    salvar(desenhar(MORANGO, CORES), "Itens/morango.png")
    salvar(tile(COM, 10), "Itens/bolacha.png")
    salvar(desenhar(CASTANHA, CORES), "Itens/castanha.png")
    salvar(gota((110, 60, 30, 255)), "Itens/calda_chocolate.png")
    salvar(gota((225, 150, 50, 255)), "Itens/calda_caramelo.png")
    salvar(gota((110, 210, 150, 255)), "Itens/calda_menta.png")
    salvar(tingir(tile(COM, 107), (255, 255, 255), (215, 215, 225)), "Itens/chantilly.png")
    salvar(desenhar(CEREJA, CORES), "Itens/cereja.png")
    salvar(desenhar(MEL, CORES), "Itens/mel.png")
    salvar(desenhar(GRANULADO, CORES), "Itens/granulado.png")
    # chão: 80 x 45 ladrilhos de 16 px, ampliados 3x (uma imagem de 1280 x 720)
    rnd = random.Random(7)
    chao = Image.new("RGBA", (427, 240))
    pisos = [tile(FAB, n) for n in (0, 0, 0, 1, 2)]
    escuro = tile(FAB, 3)
    esteira = [tile(FAB, n) for n in (25, 26, 27)]
    for ty in range(15):
        for tx in range(27):
            t = escuro if tx >= 23 else rnd.choice(pisos)          # faixa escura: fila dos clientes
            chao.paste(t, (tx * 16, ty * 16), t)
    for tx in range(23):
        t = esteira[0 if tx == 0 else (2 if tx == 22 else 1)]
        chao.paste(t, (tx * 16, 0), t)
    d = ImageDraw.Draw(chao)
    d.rectangle((16, 74, 360, 75), fill=(150, 100, 60, 255))        # faixa da linha de produção
    salvar(chao.crop((0, 0, 427, 240)).resize((1281, 720), Image.NEAREST), "Mapa/chao.png")


# --- cena e prefab -------------------------------------------------------------------------
def objeto(nome, x=0.0, y=0.0, componentes=(), escala=1.0, tag="", ativo=True, filhos=()):
    return {"nome": nome, "tag": tag, "ativo": ativo,
            "transform": {"x": float(x), "y": float(y), "rotacao": 0.0, "escala_x": escala, "escala_y": escala},
            "componentes": [{"tipo": t, "campos": c} for t, c in componentes], "filhos": list(filhos)}


def sprite(img, camada=2, **kw):
    return ("SpriteRenderer", {"imagem": img, "camada": camada, **kw})


def estacao(nome, x, y, img, titulo, ativo=False):
    return objeto(nome, x, y, [sprite(f"Assets/Sprites/Estacoes/{img}.png"),
                               ("Estacao", {"nome_dsl": nome, "titulo": titulo})], escala=5.0, ativo=ativo)


ESTACOES = [  # nome, x, y, imagem, título — a linha de produção da esquerda para a direita
    ("armazem", 110, 600, "armazem", "Armazém"),
    ("maquina", 260, 600, "maquina", "Máquina de sorvete"),
    ("massas", 410, 600, "massas", "Massas"),
    ("batedeira", 560, 600, "batedeira", "Batedeira"),
    ("caldas", 710, 600, "caldas", "Caldas"),
    ("coberturas", 860, 600, "coberturas", "Coberturas"),
    ("balcao", 1020, 600, "balcao", "Balcão"),
    ("bancada1", 330, 410, "bancada", "Bancada 1"),
    ("bancada2", 560, 410, "bancada", "Bancada 2"),
    ("bancada3", 790, 410, "bancada", "Bancada 3"),
]


def gerar_cena():
    objs = [objeto("Câmera", 640, 360, [("CameraPrincipal", {"zoom": 1.0, "cor_fundo": [0.1, 0.09, 0.11, 1.0]})]),
            objeto("Chão", 640, 360, [sprite("Assets/Sprites/Mapa/chao.png", camada=0, estatico=True)])]
    objs += [estacao(*e, ativo=e[0] == "armazem") for e in ESTACOES]
    # o ServicoAgentes vem antes da Fábrica: ela cria o primeiro robô ao iniciar
    objs.append(objeto("Agentes (DSL)", 0, 0, [("ServicoAgentes", {"arquivo": "Assets/Agentes/fabrica.agt"})]))
    objs.append(objeto("Fábrica", 0, 0, [("Fabrica", {"dinheiro_inicial": 0, "salvar": True}), ("Painel", {}),
                                         ("Tutorial", {})]))
    (PROJ / "Assets/Cenas/Principal.cena").write_text(
        json.dumps({"nome": "Principal", "objetos": objs}, indent=2, ensure_ascii=False), encoding="utf-8")
    robo = objeto("robo", 0, 0, [sprite("Assets/Sprites/Personagens/robo.png", camada=5), ("Robo", {})],
                  escala=4.0, tag="robo")
    (PROJ / "Assets/Prefabs").mkdir(parents=True, exist_ok=True)
    (PROJ / "Assets/Prefabs/robo.prefab").write_text(json.dumps(robo, indent=2, ensure_ascii=False), encoding="utf-8")


LEIA_ME = """FÁBRICA DE SORVETE (jogo de programação: The Farmer Was Replaced + Papa's Freezeria)

Você começa com a fábrica vazia: um robô e o armazém de casquinhas. Não dá para controlar o robô
direto: você escreve o PROGRAMA dele (AgentDSL) em janelas de código flutuantes e aperta Executar.
O tutorial (janela Informação) ensina a sintaxe: pegar e devolver uma casquinha, tratar falhas com
objetivos (+!g / -!g) e montar o primeiro sorvete.

Um sorvete passa por etapas, como no Papa's Freezeria:
  casquinha (tamanho) -> sorvete (creme/chocolate/misto) -> massa -> bater (pouco/medio/bem)
  -> calda -> coberturas -> entregar
Cada etapa pode FALHAR (a casquinha quebra, o sorvete derrama, passa do ponto...). O cliente paga
pela nota: quanto mais o sorvete se parece com o pedido, mais ele paga.

Na Árvore (T) você compra estações, opções do cardápio, partes da linguagem (condições, variáveis,
operadores, memória, relógio, comunicação, gerente), mais robôs e bancadas. Com várias janelas,
cada robô pode ter seu próprio programa e eles passam o sorvete um para o outro (multiagente).

Teclas: Ctrl+Enter executa a janela · T árvore · F1 comandos e erros comuns · Esc fecha
Editor: autocompletar (Tab/Enter, setas, Ctrl+Espaço) e quebra de linha automática.
Atalhos do VS Code: Ctrl+A, Shift/Ctrl+Shift+setas, mouse (arrastar, 2/3 cliques), Ctrl+C/X/V,
Ctrl+Z/Y, Ctrl+D, Ctrl+L, Alt+setas, Ctrl+Shift+K, Ctrl+/, Tab/Shift+Tab, Ctrl+F (lista completa no F1).
Janelas: arraste pela barra e redimensione puxando qualquer borda.
Progresso salvo em Saves/progresso.json (menu ≡ > Recomeçar do zero).

Onde está cada coisa:
- Assets/Scripts/Itens.py        -> cardápio, preços e as percepções que a DSL conhece
- Assets/Scripts/Robo.py         -> fila de comandos, objetivos (pilha), falhas, bancadas, avisar
- Assets/Scripts/Fabrica.py      -> clientes, pedidos, nota, árvore, salvamento, HUD
- Assets/Scripts/Desbloqueios.py -> árvore, verificação da AST (recursos bloqueados), tela F1
- Assets/Scripts/Erros.py        -> mensagens amigáveis para os erros comuns
- Assets/Scripts/Painel.py       -> janelas, compilação das janelas, telas (início, árvore...)
- Assets/Scripts/Janelas.py      -> janelas flutuantes (arrastar, redimensionar, minimizar)
- Assets/Scripts/Tutorial.py     -> passos do tutorial
- Solucoes/                      -> programas prontos (spoiler!)

Sprites: Kenney (Tiny Factory e Pixel Platformer Food Expansion), licença CC0.
"""


def main():
    Projeto.criar(PROJ, "Fábrica de Sorvete")
    (PROJ / "projeto.json").write_text(json.dumps({
        "nome": "Fábrica de Sorvete", "cena_inicial": "Assets/Cenas/Principal.cena",
        "largura": 1280, "altura": 720}, indent=2, ensure_ascii=False), encoding="utf-8")
    for velho in (SPR / "Itens").glob("*.png") if (SPR / "Itens").exists() else []:
        velho.unlink()
    gerar_sprites()
    gerar_cena()
    (PROJ / "LEIA-ME.txt").write_text(LEIA_ME, encoding="utf-8")
    print("ProjetoSorveteria gerado.")


if __name__ == "__main__":
    main()
