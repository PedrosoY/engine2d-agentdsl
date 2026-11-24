"""Monta o ProjetoPlataforma (uma fase estilo Mario) USANDO O EDITOR, com o robô.

Como no montar_navinha.py: tudo pelo editor (pastas, importação, scripts, agente, prefabs arrastados
para o Project, Inspector, Configurações do projeto, cenas). A fase é desenhada no arquivo de texto
Assets/Fases/fase1.mapa (componente MapaTiles), que pode ser editado no VS Code com a Scene aberta.

    python montar_plataforma.py          # usa assets/plataforma_fonte
    python montar_plataforma.py --ver    # mostra o editor enquanto o robô trabalha
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))
os.environ.setdefault("ENGINE2D_SEM_RECENTES", "1")

from editor_visual.montador import Montador  # noqa: E402

KENNEY = RAIZ / "assets" / "kenney_platformer"
SPR = KENNEY / "Sprites"
DESTINO = RAIZ / "ProjetoPlataforma"
T = "Assets/Sprites/Tiles/"
IN = "Assets/Sprites/Inimigos/"

PERSONAGEM = [f"character_green_{n}.png" for n in ("idle", "walk_a", "walk_b", "jump", "hit")]
INIMIGOS = ["slime_normal_walk_a", "slime_normal_walk_b", "slime_normal_rest", "slime_normal_flat",
            "snail_walk_a", "snail_walk_b", "snail_shell", "snail_rest", "bee_a", "bee_b", "bee_rest",
            "frog_idle", "frog_jump", "frog_rest"]
TILES = ["terrain_grass_block_top", "terrain_grass_block_top_left", "terrain_grass_block_top_right",
         "terrain_grass_block_center", "terrain_grass_block_left", "terrain_grass_block_right",
         "terrain_stone_block", "bricks_brown", "terrain_grass_cloud_left", "terrain_grass_cloud_middle",
         "terrain_grass_cloud_right", "block_coin", "block_exclamation", "block_empty", "coin_gold",
         "coin_gold_side", "mushroom_red", "spikes", "spring", "spring_out", "flag_off", "flag_green_a",
         "flag_green_b", "bush", "rock", "sign_right", "fence", "star", "hud_player_green", "hud_coin"]
SONS = ["sfx_jump", "sfx_jump-high", "sfx_coin", "sfx_bump", "sfx_hurt", "sfx_magic", "sfx_disappear",
        "sfx_throw", "sfx_select", "sfx_gem"]
SCRIPTS = ["Plataforma", "AcoesPlataforma", "Jogador", "Inimigo", "Objetos", "Hud", "Menu"]

CAMADAS = ["Fundo", "Cenario", "Padrao", "Frente"]
TAGS = ["jogador", "inimigo", "chao", "item", "bloco", "perigo"]
NAO_COLIDEM = ["toque:chao", "toque:toque", "toque:inimigo", "toque:item", "jogador:inimigo",
               "inimigo:inimigo", "inimigo:item", "item:item", "perigo:chao", "perigo:inimigo"]
CEU = (0.765, 0.89, 1.0, 1.0)


class MontadorPlataforma(Montador):
    def inimigo(self, nome, imagem, animacoes, caixa, dy, voa=False):
        """Prefab de inimigo: corpo dinâmico que anda no chão + filho "toque" (gatilho) que machuca."""
        self.sprite(imagem, 600, 400, nome, "Sprites", "Inimigos")
        self.campos("GameObject", tag="inimigo")
        self.campos("SpriteRenderer", ordem=5)
        self.comp("CorpoRigido", escala_gravidade=0 if voa else 1, velocidade_maxima=1400)
        self.comp("Colisor", forma="caixa", largura=caixa[0], altura=caixa[1], dy=dy, camada_fisica="inimigo")
        anims = "; ".join(f"{k}=" + ",".join(IN + q + ".png" for q in v) for k, v in animacoes.items())
        self.comp("Inimigo", animacoes=anims)
        self.comp("ComportamentoAgente", modelo=nome, olhar_movimento=False)
        self.filho(nome, "toque")
        self.campos("GameObject", tag="inimigo")
        self.comp("Colisor", forma="caixa", largura=caixa[0] - 6, altura=caixa[1] - 4, dy=dy, gatilho=True,
                  camada_fisica="toque")
        self.prefab(nome)

    def coletavel(self, nome, imagem, tipo, quadros="", gatilho=True, corpo=False):
        self.sprite(imagem, 600, 400, nome, "Sprites", "Tiles")
        self.campos("GameObject", tag="item")
        self.campos("SpriteRenderer", ordem=3)
        if corpo:
            self.comp("CorpoRigido", velocidade_maxima=1400)
        if gatilho is not None:
            self.comp("Colisor", forma="caixa", largura=44, altura=44, gatilho=gatilho, camada_fisica="item")
        self.comp("Coletavel", tipo=tipo, quadros=quadros)
        self.prefab(nome)

    def bloco(self, nome, imagem):
        self.sprite(imagem, 600, 400, nome, "Sprites", "Tiles")
        self.campos("GameObject", tag="bloco")
        self.comp("Colisor", forma="caixa", largura=64, altura=64, camada_fisica="chao")
        self.comp("Bloco")
        self.comp("ComportamentoAgente", modelo=nome, olhar_movimento=False)
        self.prefab(nome)

    def particulas(self, nome, imagem, **campos):
        self.vazio(nome, 600, 400)
        self.comp("EmissorParticulas", imagem=imagem, taxa=0, emitindo=False, destruir_ao_fim=True,
                  camada_desenho="Frente", **campos)
        self.prefab(nome)

    def ceu(self, pai):
        """Fundo com paralaxe: filho da câmera, anda só 15% do que a câmera anda."""
        self.filho(pai, "Ceu")
        self.campos("Transform", y=-104)
        self.comp("FundoRolante", imagem="Assets/Sprites/Fundos/background_clouds.png", escala=2,
                  largura=1500, altura=512, velocidade_x=-12, velocidade_y=0, paralaxe=0.15, repetir_y=False,
                  camada_desenho="Fundo", camada=0)

    # --- o roteiro --------------------------------------------------------------------------------------
    def montar(self):
        r, app = self.r, self.app
        print("1. configurações do projeto, pastas e arquivos")
        self.configurar(camadas_desenho=CAMADAS, tags=TAGS, gravidade_y=-2000, colisoes_ignoradas=NAO_COLIDEM)
        p = app.projeto
        assert p.camadas_desenho == CAMADAS and p.gravidade == (0.0, -2000.0), (p.camadas_desenho, p.gravidade)
        self.puxar_divisoria()
        self.importar_em("Sprites/Personagem", [SPR / "Characters/Default" / f for f in PERSONAGEM])
        self.importar_em("Sprites/Inimigos", [SPR / "Enemies/Default" / f"{n}.png" for n in INIMIGOS])
        self.importar_em("Sprites/Tiles", [SPR / "Tiles/Default" / f"{n}.png" for n in TILES])
        self.importar_em("Sprites/Fundos", [SPR / "Backgrounds/Default/background_clouds.png"])
        self.abrir_pasta("Sprites")
        app.importar_arquivo(KENNEY / "License.txt")
        (p.raiz / "Assets/Sprites/License.txt").rename(p.raiz / "Assets/Sprites/LICENCA_Kenney.txt")
        shutil.copy(self.fonte / "LEIA-ME.txt", p.raiz / "LEIA-ME.txt")
        self.importar_em("Sons", [KENNEY / "Sounds" / f"{s}.ogg" for s in SONS])
        self.importar_em("Fases", sorted((self.fonte / "Fases").glob("*.mapa")))

        print("2. scripts e agente")
        self.abrir_pasta("Scripts")
        for s in SCRIPTS:
            self.criar_script(s)
        self.esperar_scripts()
        print("   ", self.criar_agente("plataforma"))

        print("3. prefabs")
        self.particulas("poeira", "embutido:circulo", rajada=6, vida=0.35, velocidade=70, angulo=90,
                        espalhamento=160, tamanho_inicial=0.3, tamanho_final=0.05, cor_inicial=(1, 1, 1, 0.9),
                        cor_final=(1, 1, 1, 0), gravidade=-60)
        self.particulas("brilho", f"{T}star.png", rajada=8, vida=0.4, velocidade=140, tamanho_inicial=0.45,
                        tamanho_final=0.05, cor_inicial=(1, 0.95, 0.4, 1), cor_final=(1, 0.95, 0.4, 0), girar=300)
        moeda = f"{T}coin_gold.png,{T}coin_gold_side.png"
        self.coletavel("moeda", "coin_gold.png", "moeda", quadros=moeda)
        self.coletavel("moeda_bloco", "coin_gold.png", "moeda_bloco", quadros=moeda, gatilho=None, corpo=True)
        self.coletavel("cogumelo", "mushroom_red.png", "cogumelo", gatilho=False, corpo=True)
        self.bloco("bloco_moeda", "block_coin.png")
        self.bloco("bloco_cogumelo", "block_exclamation.png")
        self.inimigo("slime", "slime_normal_walk_a.png",
                     {"andar": ["slime_normal_walk_a", "slime_normal_walk_b"], "parado": ["slime_normal_rest"],
                      "achatado": ["slime_normal_flat"]}, (52, 40), -10)
        self.inimigo("caracol", "snail_walk_a.png",
                     {"andar": ["snail_walk_a", "snail_walk_b"], "parado": ["snail_rest"],
                      "concha": ["snail_shell"], "achatado": ["snail_shell"]}, (56, 44), -8)
        self.inimigo("abelha", "bee_a.png", {"voar": ["bee_a", "bee_b"], "parado": ["bee_rest"],
                                            "achatado": ["bee_rest"]}, (50, 44), 0, voa=True)
        self.inimigo("sapo", "frog_idle.png", {"parado": ["frog_idle"], "pulo": ["frog_jump"],
                                              "achatado": ["frog_rest"]}, (50, 44), -8)
        self.sprite("spikes.png", 600, 400, "espinhos", "Sprites", "Tiles")
        self.campos("GameObject", tag="perigo")
        self.comp("Colisor", forma="caixa", largura=56, altura=24, dy=-18, gatilho=True, camada_fisica="perigo")
        self.prefab("espinhos")
        self.sprite("spring.png", 600, 400, "mola", "Sprites", "Tiles")
        self.comp("Colisor", forma="caixa", largura=50, altura=30, dy=-16, gatilho=True, camada_fisica="item")
        self.comp("Mola")
        self.prefab("mola")
        self.sprite("flag_off.png", 600, 400, "checkpoint", "Sprites", "Tiles")
        self.comp("Colisor", forma="caixa", largura=40, altura=120, gatilho=True, camada_fisica="item")
        self.comp("Checkpoint", quadros_ativo=f"{T}flag_green_a.png,{T}flag_green_b.png")
        self.prefab("checkpoint")
        self.sprite("flag_green_a.png", 600, 400, "bandeira", "Sprites", "Tiles")
        self.comp("Colisor", forma="caixa", largura=50, altura=400, gatilho=True, camada_fisica="item")
        self.comp("Bandeira", quadros=f"{T}flag_green_a.png,{T}flag_green_b.png")
        self.prefab("bandeira")

        print("4. cena da fase")
        self.selecionar("Câmera")
        self.campos("Transform", x=480, y=400)
        self.campos("CameraPrincipal", zoom=0.75, cor_fundo=CEU)
        self.comp("CameraPlataforma")
        self.ceu("Câmera")
        app._enquadrar_camera_inicial()
        self.vazio("Decoracao", 0, 768)
        self.comp("MapaTiles", arquivo="Assets/Fases/fase1_decoracao.mapa", camada_desenho="Cenario")
        self.vazio("Mapa", 0, 768)
        self.comp("MapaTiles", camada_fisica="chao", tag_colisores="chao")
        self.abrir_pasta("Fases")                         # arrasta o .mapa até o campo "arquivo"
        r.arrastar(r.item_projeto("fase1.mapa"), r.campo_inspector("arquivo", "MapaTiles"))
        assert app.selecionado.obter("MapaTiles").arquivo == "Assets/Fases/fase1.mapa"
        self.sprite("character_green_idle.png", 160, 240, "Jogador", "Sprites", "Personagem")
        self.campos("GameObject", tag="jogador")
        self.campos("Transform", escala_x=0.75, escala_y=0.75)
        self.campos("SpriteRenderer", ordem=10)
        self.comp("CorpoRigido", velocidade_maxima=1500)
        self.comp("Colisor", forma="caixa", largura=60, altura=92, dy=-12, camada_fisica="jogador")
        self.comp("Jogador")
        self.vazio("HUD")
        self.comp("Hud")
        self.vazio("Agentes")
        self.comp("ServicoAgentes", arquivo="Assets/Agentes/plataforma.agt")
        self.abrir_pasta("Cenas")
        self.salvar_cena_como("Fase1")
        r.capturar(DESTINO / "Library" / "editor_fase.png")

        print("5. cena do menu")
        self.apagar_asset("Principal.cena")
        r.menu("Arquivo", "Nova cena")
        self.selecionar("Câmera")
        self.campos("Transform", x=640, y=360)
        self.campos("CameraPrincipal", zoom=0.75, cor_fundo=CEU)
        self.ceu("Câmera")
        self.vazio("Chao", 0, 640)
        self.comp("MapaTiles", arquivo="Assets/Fases/menu.mapa")
        self.sprite("character_green_jump.png", 330, 230, "Personagem", "Sprites", "Personagem")
        self.campos("SpriteRenderer", ordem=10)
        self.sprite("slime_normal_walk_a.png", 900, 160, "Slime", "Sprites", "Inimigos")
        self.campos("SpriteRenderer", virar_x=True)
        self.vazio("Menu")
        self.comp("Menu")
        self.salvar_cena_como("Menu")
        r.menu("Arquivo", "Definir como cena inicial")
        assert app.projeto.cena_inicial == "Assets/Cenas/Menu.cena"
        r.capturar(DESTINO / "Library" / "editor_menu.png")
        print("pronto:", DESTINO)
        return self.erros_no_console()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    fonte = Path(args[0]) if args else RAIZ / "assets" / "plataforma_fonte"
    m = MontadorPlataforma(DESTINO, "Pulo Verde", fonte, largura=960, altura=540, ver="--ver" in sys.argv)
    try:
        for e in m.montar():
            print("ERRO NO CONSOLE:", e)
    except Exception:
        (RAIZ / "resultados").mkdir(exist_ok=True)
        m.r.capturar(RAIZ / "resultados" / "montar_plataforma_erro.png")
        print("\n".join(m.r.console(12)))
        raise
    finally:
        m.fechar()


if __name__ == "__main__":
    main()
