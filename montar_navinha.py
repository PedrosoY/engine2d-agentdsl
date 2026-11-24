"""Monta o ProjetoNavinha USANDO O EDITOR, com o robô (mouse e teclado simulados).

Nada de escrever cena ou prefab em JSON na mão: o robô cria as pastas no painel Project, importa os
arquivos (como arrastar do Windows), cria os scripts e o agente pelo menu do Project, arrasta as
imagens para a Scene, renomeia com F2, preenche o Inspector, adiciona componentes pelo botão,
arrasta objetos para o Project para virarem prefabs e salva as cenas com Ctrl+S.
O código dos scripts e do .agt vem da pasta ``fonte`` (é o que a pessoa digitaria no VS Code).

    python montar_navinha.py            # usa assets/navinha_fonte (Scripts/, Agentes/, explosao.wav)
    python montar_navinha.py --ver      # mostra a janela do editor enquanto o robô trabalha
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("ENGINE2D_SEM_RECENTES", "1")

from editor_unity.montador import Montador  # noqa: E402

KENNEY = RAIZ / "assets" / "kenney_space"
DESTINO = RAIZ / "ProjetoNavinha"

SPRITES = {
    "Naves": ["PNG/playerShip1_blue.png"],
    "Inimigos": ["PNG/Enemies/enemyBlack1.png", "PNG/Enemies/enemyBlue3.png", "PNG/Enemies/enemyRed2.png",
                 "PNG/ufoRed.png"],
    "Meteoros": ["PNG/Meteors/meteorBrown_big1.png", "PNG/Meteors/meteorBrown_small1.png"],
    "Tiros": ["PNG/Lasers/laserBlue01.png", "PNG/Lasers/laserRed08.png"],
    "Efeitos": ["PNG/Effects/star1.png", "PNG/Effects/star3.png", "PNG/Effects/fire00.png",
                "PNG/Effects/shield1.png"],
    "Itens": ["PNG/Power-ups/powerupBlue_bolt.png", "PNG/Power-ups/powerupGreen_shield.png",
              "PNG/Power-ups/pill_red.png", "PNG/Power-ups/star_gold.png"],
    "Fundos": ["Backgrounds/darkPurple.png", "Backgrounds/black.png"],
    "UI": ["PNG/UI/playerLife1_blue.png"],
}
SONS = ["Bonus/sfx_laser1.ogg", "Bonus/sfx_laser2.ogg", "Bonus/sfx_zap.ogg", "Bonus/sfx_shieldUp.ogg",
        "Bonus/sfx_shieldDown.ogg", "Bonus/sfx_lose.ogg", "Bonus/sfx_twoTone.ogg"]
FONTES = ["Bonus/kenvector_future.ttf"]
SCRIPTS = ["Navinha", "AcoesNave", "Jogador", "Tiro", "NaveInimiga", "Item", "Hud", "Fase", "Menu"]

COR_ITEM = {"arma": (0.4, 0.7, 1, 1), "escudo": (0.4, 1, 0.5, 1), "vida": (1, 0.4, 0.4, 1),
            "pontos": (1, 0.85, 0.3, 1)}

IGNORAR = ("tiro_jogador:tiro_jogador, tiro_inimigo:tiro_inimigo, tiro_jogador:tiro_inimigo, "
           "tiro_jogador:jogador, tiro_jogador:item, tiro_inimigo:inimigo, tiro_inimigo:item, "
           "inimigo:inimigo, inimigo:item, item:item")


class MontadorNavinha(Montador):
    def nave_inimiga(self, nome, imagem, raio, escala=0.55, vida_visual=1.0, kamikaze=False):
        pasta = "Meteoros" if "meteor" in imagem else "Inimigos"
        self.sprite(imagem, 450, 300, nome, "Sprites", pasta)
        self.campos("GameObject", tag="inimigo")
        self.campos("Transform", escala_x=escala, escala_y=escala)
        self.campos("SpriteRenderer", ordem=3)
        self.comp("CorpoRigido", tipo="cinematico")
        self.comp("Colisor", raio=raio, gatilho=True, camada_fisica="inimigo")
        self.comp("NaveInimiga", tamanho_explosao=vida_visual)
        self.comp("Piscar")
        self.comp("ComportamentoAgente", olhar_movimento=kamikaze, frente_do_sprite=-90 if kamikaze else 0)
        self.comp("ProjetorSombra2D")                  # bloqueia as luzes da nave (sombras)
        if nome == "chefe":
            self.comp("Luz2D", cor=(1, 0.25, 0.2, 1), intensidade=1.5, raio=280, piscar=0.35)
        self.prefab(nome)

    def item(self, nome, imagem, tipo):
        self.sprite(imagem, 450, 300, nome, "Sprites", "Itens")
        self.campos("GameObject", tag="item")
        self.campos("SpriteRenderer", ordem=4, receber_luz=False)
        self.comp("Colisor", raio=16, gatilho=True, camada_fisica="item")
        self.comp("Item", tipo=tipo)
        self.comp("Luz2D", cor=COR_ITEM[tipo], intensidade=0.9, raio=90)
        self.prefab(nome)

    def fundo(self, imagem, vel):
        self.vazio("Fundo", 450, 300)
        self.comp("FundoRolante", imagem=f"Assets/Sprites/Fundos/{imagem}", velocidade_y=vel, largura=900,
                  altura=600, camada=-100)
        self.vazio("Estrelas", 450, 640)
        self.comp("EmissorParticulas", imagem="Assets/Sprites/Efeitos/star3.png", taxa=7, vida=3.4,
                  vida_variacao=0.2, velocidade=230, velocidade_variacao=0.5, angulo=-90, espalhamento=0,
                  tamanho_inicial=0.35, tamanho_final=0.35, cor_inicial=(1, 1, 1, 0.7), cor_final=(1, 1, 1, 0.7),
                  camada_desenho="Fundo", camada=-50, area_largura=900, receber_luz=False, aditivo=True)

    # --- o roteiro ------------------------------------------------------------------------------------
    def montar(self):
        r, app = self.r, self.app
        print("1. configurações, pastas e arquivos")
        self.configurar(gravidade_y=0, tags=["jogador", "inimigo", "item", "tiro"])   # jogo visto de cima
        self.puxar_divisoria()
        self.abrir_pasta("Sprites")
        for pasta, arquivos in SPRITES.items():
            self.abrir_pasta("Sprites")
            self.criar_pasta(pasta)
            self.abrir_pasta("Sprites", pasta)
            self.importar(KENNEY / a for a in arquivos)
        self.abrir_pasta("Sprites")
        app.importar_arquivo(KENNEY / "license.txt")
        (app.projeto.raiz / "Assets/Sprites/license.txt").rename(app.projeto.raiz / "Assets/Sprites/LICENCA_Kenney.txt")
        shutil.copy(self.fonte / "LEIA-ME.txt", app.projeto.raiz / "LEIA-ME.txt")
        self.importar_em("Sons", [KENNEY / s for s in SONS] + [self.fonte / "explosao.wav"])
        self.importar_em("Fontes", [KENNEY / f for f in FONTES])

        print("2. scripts e agente (menu do Project)")
        self.abrir_pasta("Scripts")
        for s in SCRIPTS:
            self.criar_script(s)
        self.esperar_scripts()
        print("   ", self.criar_agente("navinha"))

        print("3. prefabs")
        self.sprite("laserBlue01.png", 450, 300, "tiro_jogador", "Sprites", "Tiros")
        self.campos("GameObject", tag="tiro")
        self.campos("SpriteRenderer", ordem=4, receber_luz=False, aditivo=True)
        self.comp("CorpoRigido", tipo="cinematico")
        self.comp("Colisor", forma="caixa", largura=9, altura=40, gatilho=True, camada_fisica="tiro_jogador")
        self.comp("Tiro", do_jogador=True, dano=1)
        self.comp("Luz2D", cor=(0.35, 0.65, 1, 1), intensidade=1.0, raio=90)
        self.prefab("tiro_jogador")

        self.sprite("laserRed08.png", 450, 300, "tiro_inimigo", "Sprites", "Tiros")
        self.campos("GameObject", tag="tiro")
        self.campos("Transform", escala_x=0.4, escala_y=0.4)
        self.campos("SpriteRenderer", ordem=6, receber_luz=False)
        self.comp("CorpoRigido", tipo="cinematico")
        self.comp("Colisor", raio=16, gatilho=True, camada_fisica="tiro_inimigo")
        self.comp("Tiro", do_jogador=False)
        self.comp("Luz2D", cor=(1, 0.3, 0.25, 1), intensidade=1.0, raio=75)
        self.prefab("tiro_inimigo")

        self.vazio("explosao", 450, 300)
        self.comp("EmissorParticulas", imagem="Assets/Sprites/Efeitos/star1.png", rajada=36, taxa=0,
                  emitindo=False, vida=0.7, velocidade=170, velocidade_variacao=0.8, tamanho_inicial=1.5,
                  tamanho_final=0.1, cor_inicial=(1, 0.85, 0.35, 1), cor_final=(1, 0.15, 0, 0), arrasto=2.5,
                  girar=200, camada_desenho="Frente", camada=8, destruir_ao_fim=True, receber_luz=False,
                  aditivo=True)
        self.comp("Luz2D", cor=(1, 0.6, 0.25, 1), intensidade=2.6, raio=300, raio_interno=0.15, apagar_em=0.6)
        self.prefab("explosao")

        self.vazio("faisca", 450, 300)
        self.comp("EmissorParticulas", imagem="Assets/Sprites/Efeitos/star1.png", rajada=6, taxa=0,
                  emitindo=False, vida=0.25, velocidade=140, tamanho_inicial=0.6, tamanho_final=0.1,
                  cor_inicial=(0.6, 0.9, 1, 1), cor_final=(0.6, 0.9, 1, 0), camada_desenho="Frente", camada=7,
                  destruir_ao_fim=True, receber_luz=False, aditivo=True)
        self.prefab("faisca")

        self.nave_inimiga("batedor", "enemyBlack1.png", 38)
        self.nave_inimiga("atirador", "enemyBlue3.png", 40, vida_visual=1.3)
        self.nave_inimiga("kamikaze", "enemyRed2.png", 36, kamikaze=True)
        self.nave_inimiga("meteoro", "meteorBrown_big1.png", 44, escala=0.6, vida_visual=1.2)
        self.nave_inimiga("pedrinha", "meteorBrown_small1.png", 13, escala=0.9, vida_visual=0.5)
        self.nave_inimiga("chefe", "ufoRed.png", 44, escala=1.5, vida_visual=3.0)
        self.item("item_arma", "powerupBlue_bolt.png", "arma")
        self.item("item_escudo", "powerupGreen_shield.png", "escudo")
        self.item("item_vida", "pill_red.png", "vida")
        self.item("item_pontos", "star_gold.png", "pontos")

        print("4. cena da fase")
        self.selecionar("Câmera")
        self.campos("Transform", x=450, y=300)
        self.campos("CameraPrincipal", cor_fundo=(0, 0, 0, 1))
        app._enquadrar_camera_inicial()
        self.fundo("darkPurple.png", -45)
        self.vazio("Luz ambiente", 450, 300)            # o espaço fica escuro; o resto vem das luzes
        self.comp("Luz2D", tipo="global", cor=(0.55, 0.5, 0.9, 1), intensidade=0.5)

        self.sprite("playerShip1_blue.png", 450, 80, "Jogador", "Sprites", "Naves")
        self.campos("GameObject", tag="jogador")
        self.campos("Transform", escala_x=0.5, escala_y=0.5)
        self.campos("SpriteRenderer", ordem=5)
        self.comp("Colisor", raio=20, gatilho=True, camada_fisica="jogador")
        self.comp("Jogador")
        self.comp("Luz2D", cor=(0.55, 0.75, 1, 1), intensidade=1.7, raio=280, raio_interno=0.1, sombras=True)
        self.filho("Jogador", "Fogo")
        self.campos("Transform", y=-62)
        self.comp("EmissorParticulas", imagem="Assets/Sprites/Efeitos/fire00.png", taxa=45, vida=0.22,
                  velocidade=150, velocidade_variacao=0.3, angulo=-90, espalhamento=18, tamanho_inicial=0.7,
                  tamanho_final=0.1, cor_inicial=(1, 0.85, 0.4, 1), cor_final=(1, 0.2, 0, 0), camada=4,
                  receber_luz=False, aditivo=True)
        self.comp("Luz2D", cor=(1, 0.55, 0.2, 1), intensidade=0.9, raio=110, piscar=0.4)
        self.filho("Jogador", "Farol")                  # lanterna para a frente, com sombras
        self.campos("Transform", y=50)
        self.comp("Luz2D", tipo="cone", cor=(0.95, 0.95, 1, 1), intensidade=2.6, raio=560, angulo=90,
                  abertura=58, sombras=True)
        self.filho("Jogador", "Escudo", "Criar filho sprite")
        self.campos("SpriteRenderer", imagem="Assets/Sprites/Efeitos/shield1.png", ordem=6, receber_luz=False,
                    aditivo=True)
        self.campos("Transform", escala_x=1.1, escala_y=1.1)
        caixa = r.campo_inspector("nome", "GameObject")       # a caixinha "ativo" fica à esquerda do nome
        nome_r = next(rr for rr, alvo, c, _ in app._campos_insp if c == "nome")
        r.clicar(nome_r.x - 16, caixa[1])
        assert not app.selecionado.ativo

        self.vazio("HUD")
        self.comp("Hud")
        self.vazio("Agentes")
        self.comp("ServicoAgentes")
        # arrasta o .agt do Project até o campo "arquivo" do Inspector
        self.abrir_pasta("Agentes")
        r.arrastar(r.item_projeto("navinha.agt"), r.campo_inspector("arquivo", "ServicoAgentes"))
        assert app.selecionado.obter("ServicoAgentes").arquivo == "Assets/Agentes/navinha.agt"
        self.vazio("Regras")
        self.comp("CamadasFisica", ignorar=IGNORAR)
        self.comp("Fase")
        self.abrir_pasta("Cenas")
        self.salvar_cena_como("Fase1")

        print("5. cena do menu")
        self.apagar_asset("Principal.cena")                 # a cena vazia do projeto novo
        assert not (app.projeto.raiz / "Assets/Cenas/Principal.cena").exists()
        r.menu("Arquivo", "Nova cena")
        self.selecionar("Câmera")
        self.campos("Transform", x=450, y=300)
        self.campos("CameraPrincipal", cor_fundo=(0, 0, 0, 1))
        self.fundo("black.png", -25)
        self.vazio("Luz ambiente", 450, 300)
        self.comp("Luz2D", tipo="global", cor=(0.6, 0.55, 0.9, 1), intensidade=0.55)
        self.sprite("playerShip1_blue.png", 450, 150, "Nave", "Sprites", "Naves")
        self.comp("Luz2D", cor=(0.55, 0.75, 1, 1), intensidade=1.4, raio=320)
        self.campos("Transform", escala_x=0.8, escala_y=0.8)
        self.filho("Nave", "Fogo")
        self.campos("Transform", y=-62)
        self.comp("EmissorParticulas", imagem="Assets/Sprites/Efeitos/fire00.png", taxa=45, vida=0.3,
                  velocidade=150, angulo=-90, espalhamento=18, tamanho_inicial=0.8, tamanho_final=0.1,
                  cor_inicial=(1, 0.85, 0.4, 1), cor_final=(1, 0.2, 0, 0), camada=4, receber_luz=False,
                  aditivo=True)
        self.vazio("Menu")
        self.comp("Menu")
        self.salvar_cena_como("Menu")
        r.menu("Arquivo", "Definir como cena inicial")
        assert app.projeto.cena_inicial == "Assets/Cenas/Menu.cena", app.projeto.cena_inicial
        r.capturar(DESTINO / "Library" / "editor_menu.png")
        self.abrir_pasta("Cenas")
        r.clique_duplo(*r.item_projeto("Fase1.cena"))
        r.capturar(DESTINO / "Library" / "editor_fase.png")
        print("pronto:", DESTINO)
        return self.erros_no_console()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    fonte = Path(args[0]) if args else RAIZ / "assets" / "navinha_fonte"
    m = MontadorNavinha(DESTINO, "Navinha", fonte, largura=900, altura=600, ver="--ver" in sys.argv)
    try:
        for e in m.montar():
            print("ERRO NO CONSOLE:", e)
    except Exception:
        m.r.capturar(RAIZ / "resultados" / "montar_navinha_erro.png")
        print("\n".join(m.r.console(12)))
        raise
    finally:
        m.fechar()


if __name__ == "__main__":
    main()
