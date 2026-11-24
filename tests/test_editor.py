"""Testes do sistema de projetos e do editor ."""
import shutil
import time
from pathlib import Path

import pytest

from engine2d import Cena
from engine2d.objeto import REGISTRO_COMPONENTES, ComponenteAusente
from engine2d.projeto import Projeto

RAIZ = Path(__file__).resolve().parent.parent


def test_criar_projeto_tem_pastas_e_cena(tmp_path):
    p = Projeto.criar(tmp_path / "Jogo", "Jogo")
    for pasta in ("Cenas", "Scripts", "Sprites", "Prefabs", "Agentes"):
        assert (tmp_path / "Jogo" / "Assets" / pasta).is_dir()
    assert (tmp_path / "Jogo" / "Assets/Cenas/Principal.cena").exists()
    assert p.nome == "Jogo"


def test_scripts_do_projeto_viram_componentes_e_recarregam(tmp_path):
    p = Projeto.criar(tmp_path / "Jogo")
    arq = p.criar_script(tmp_path / "Jogo/Assets/Scripts", "meu teste")
    assert arq.name == "MeuTeste.py"
    p.carregar_scripts()
    assert "MeuTeste" in p.classes_de_scripts() and "MeuTeste" in REGISTRO_COMPONENTES
    time.sleep(0.05)
    arq.write_text(arq.read_text(encoding="utf-8") + "\n(", encoding="utf-8")   # erro de sintaxe
    import os
    os.utime(arq, (time.time() + 5, time.time() + 5))
    p.carregar_scripts()
    assert p.erros_scripts and "MeuTeste.py" in p.erros_scripts[0]


def test_componente_ausente_preserva_dados():
    cena = Cena()
    cena.carregar_dict({"objetos": [{"nome": "x", "componentes": [
        {"tipo": "ScriptQueNaoExiste", "campos": {"vida": 7}}]}]})
    comp = cena.encontrar("x").componentes[0]
    assert isinstance(comp, ComponenteAusente)
    assert cena.para_dict()["objetos"][0]["componentes"][0] == {"tipo": "ScriptQueNaoExiste", "campos": {"vida": 7}}


def test_modo_edicao_nao_roda_scripts():
    from engine2d import Componente
    rodou = []

    class Conta(Componente):
        def iniciar(self):
            rodou.append(1)

    cena = Cena(modo_edicao=True)
    cena.criar("a", componentes=[Conta()])
    cena.iniciar_pendentes()
    assert rodou == []


@pytest.mark.gpu
def test_projeto_exemplo_roda_no_player():
    import rodar
    assert rodar.main([str(RAIZ / "ProjetoExemplo")], max_quadros=60) == 0


def test_nome_do_script_mantem_maiusculas(tmp_path):
    p = Projeto.criar(tmp_path / "Jogo")
    pasta = tmp_path / "Jogo/Assets/Scripts"
    assert p.criar_script(pasta, "NaveInimiga").name == "NaveInimiga.py"
    assert p.criar_script(pasta, "nave do jogador").name == "NaveDoJogador.py"


@pytest.fixture
def robo(tmp_path):
    import os
    os.environ["ENGINE2D_SEM_RECENTES"] = "1"
    from editor_visual.robo import RoboEditor
    proj = Projeto.criar(tmp_path / "Teste", "Teste")
    r = RoboEditor(proj.raiz)
    yield r
    r.fechar()


@pytest.mark.gpu
def test_robo_png_no_sprite_renderer(robo):
    """O caso que dava errado: objeto vazio + SpriteRenderer sem imagem + arrastar o PNG até o campo."""
    r, app = robo, robo.app
    png = RAIZ / "assets/kenney_space/PNG/playerShip1_blue.png"
    r.clique_duplo(*r.item_projeto("Sprites"))
    app.importar_arquivo(png)
    r.menu("GameObject", "Criar vazio")
    go = app.selecionado
    r.adicionar_componente("SpriteRenderer")               # sem imagem: não pode travar o editor
    sr = go.obter("SpriteRenderer")
    assert sr is not None and sr.sprite is not None
    assert not [l for l in r.console(20) if l.startswith("[erro]")]
    r.arrastar(r.item_projeto("playerShip1_blue.png"), r.campo_inspector("imagem"))
    assert app.selecionado is go                           # clicar na imagem não desmarca o objeto
    assert sr.imagem == "Assets/Sprites/playerShip1_blue.png"
    assert sr.sprite.textura.largura == 99                 # a textura nova foi carregada de verdade
    # um clique sem arrastar seleciona o arquivo (Inspector mostra a imagem)
    r.clicar(*r.item_projeto("playerShip1_blue.png"))
    assert app.asset_selecionado is not None and app.selecionado is None


@pytest.mark.gpu
def test_robo_soltar_imagem_e_script_no_objeto(robo):
    r, app = robo, robo.app
    r.clique_duplo(*r.item_projeto("Sprites"))
    app.importar_arquivo(RAIZ / "assets/kenney_space/PNG/ufoRed.png")
    r.menu("GameObject", "Criar vazio")
    go = app.selecionado
    r.arrastar(r.item_projeto("ufoRed.png"), r.centro("insp"))      # solto em qualquer lugar do Inspector
    assert go.obter("SpriteRenderer").imagem.endswith("ufoRed.png")
    r.clicar(*r.pasta_projeto("Scripts"))
    app.projeto.criar_script(app.projeto.raiz / "Assets/Scripts", "Girador")
    app.recarregar_scripts(forcar=True)
    r.arrastar(r.item_projeto("Girador.py"), r.linha_hierarquia(go.nome))   # solto na Hierarchy
    assert go.obter("Girador") is not None


@pytest.mark.gpu
def test_robo_menu_nao_escolhe_item_com_o_mesmo_clique(robo):
    """Abrir "Adicionar Componente" perto do fim da tela não pode já adicionar o item que cai sob o mouse."""
    r, app = robo, robo.app
    r.menu("GameObject", "Sprite")
    go = app.selecionado
    for nome in ("CorpoRigido", "Colisor", "Piscar", "TempoDeVida"):
        r.adicionar_componente(nome)
        assert type(go.componentes[-1]).__name__ == nome, [type(c).__name__ for c in go.componentes]


@pytest.mark.gpu
def test_robo_campos_prefab_e_cena(robo):
    r, app = robo, robo.app
    r.menu("GameObject", "Sprite com física")
    go = app.selecionado
    r.tecla("f2")
    r.responder("nave")
    r.preencher("escala_x", "0.5", "Transform")
    r.preencher("raio", "12", "Colisor")
    r.marcar("gatilho", True, "Colisor")
    r.preencher("camada_fisica", "inimigo", "Colisor")
    c = go.obter("Colisor")
    assert (go.nome, go.transform.escala_x, c.raio, c.gatilho, c.camada_fisica) == ("nave", 0.5, 12.0, True, "inimigo")
    r.tecla("z", mods=("ctrl",))                            # Ctrl+Z desfaz o último campo
    assert app.cena.encontrar("nave").obter("Colisor").camada_fisica == "padrao"
    r.clicar(*r.pasta_projeto("Prefabs"))
    a = app.r_baixo
    r.arrastar(r.linha_hierarquia("nave"), (a.centerx + 100, a.centery))
    assert (app.projeto.raiz / "Assets/Prefabs/nave.prefab").exists()
    r.tecla("s", mods=("ctrl",))
    assert not app.modificado and "nave" in app.caminho_cena.read_text(encoding="utf-8")


@pytest.mark.gpu
def test_robo_formas_camadas_tags_e_configuracoes(robo):
    """Sprites 2D padrão pelo menu, camada de desenho e tag escolhidas na lista, Configurações do projeto."""
    r, app = robo, robo.app
    r.menu("GameObject", "2D: Círculo")
    go = app.selecionado
    assert go.nome == "Círculo" and go.obter("SpriteRenderer").imagem == "embutido:circulo"
    r.menu("Editar", "Configurações do projeto...")
    r.preencher("camadas_desenho", "Fundo, Cenario, Padrao, Frente", "Projeto")
    r.preencher("gravidade_y", "-2000", "Projeto")
    r.preencher("tags", "jogador, inimigo, bloco", "Projeto")
    p = app.projeto
    assert p.camadas_desenho == ["Fundo", "Cenario", "Padrao", "Frente"] and p.gravidade[1] == -2000
    assert app.motor.camadas_desenho == p.camadas_desenho                  # o motor recebeu
    assert '"gravidade": [\n    0.0,\n    -2000.0' in (p.raiz / "projeto.json").read_text(encoding="utf-8")
    r.clicar(*r.linha_hierarquia("Círculo"))
    r.preencher("camada_desenho", "Cenario", "SpriteRenderer")             # lista de camadas
    r.preencher("tag", "bloco", "GameObject")                              # lista de tags
    r.preencher("tipo", "estatico", "CorpoRigido") if go.obter("CorpoRigido") else None
    assert go.obter("SpriteRenderer").camada_desenho == "Cenario" and go.tag == "bloco"
    r.adicionar_componente("CorpoRigido")
    r.preencher("tipo", "cinematico", "CorpoRigido")
    assert go.obter("CorpoRigido").tipo == "cinematico"


@pytest.mark.gpu
def test_robo_reordenar_na_hierarquia(robo):
    r, app = robo, robo.app
    for forma in ("Quadrado", "Triângulo"):
        r.menu("GameObject", f"2D: {forma}")
    nomes = lambda: [g.nome for g in app.cena.raizes()]                      # noqa: E731
    assert nomes() == ["Câmera", "Quadrado", "Triângulo"]
    # arrasta o Triângulo para a parte de cima da linha do Quadrado: entra antes dele
    rq = next(rr for rr, g in app._linhas_hier if g.nome == "Quadrado")
    r.arrastar(r.linha_hierarquia("Triângulo"), (rq.centerx, rq.y + 2))
    assert nomes() == ["Câmera", "Triângulo", "Quadrado"]
    app.cena.sincronizar_render()
    q, t = app.cena.encontrar("Quadrado"), app.cena.encontrar("Triângulo")
    assert q.indice_hierarquia > t.indice_hierarquia                       # o Quadrado agora fica na frente
    # no meio da linha: vira filho
    rq = next(rr for rr, g in app._linhas_hier if g.nome == "Quadrado")
    r.arrastar(r.linha_hierarquia("Triângulo"), rq.center)
    assert t.pai is q
    r.tecla("z", mods=("ctrl",))
    assert app.cena.encontrar("Triângulo").pai is None


@pytest.mark.gpu
def test_robo_pinta_mapa_de_tiles(robo):
    """Mapa novo pelo menu, imagem arrastada para a paleta, pintar/apagar/conta-gotas na Scene, Ctrl+Z."""
    r, app = robo, robo.app
    r.clique_duplo(*r.item_projeto("Sprites"))
    for nome in ("terrain_grass_block_top.png", "bricks_brown.png"):
        app.importar_arquivo(RAIZ / "assets/kenney_platformer/Sprites/Tiles/Default" / nome)
    r.menu("GameObject", "Mapa de tiles")
    go = app.selecionado
    mapa = go.obter("MapaTiles")
    go.transform.x, go.transform.y = 0, 256                  # canto de cima à esquerda do mapa
    r.quadros(2)
    paleta = lambda: app._r_paleta.center                     # noqa: E731
    r.campo_inspector("arquivo", "MapaTiles")                 # rola até a paleta aparecer
    r.arrastar(r.item_projeto("terrain_grass_block_top.png"), paleta())
    grama = app.pincel
    assert grama and mapa.legenda[grama]["solido"] and mapa.arquivo.endswith(".mapa")
    cs = mapa.tamanho_celula
    centro = lambda c, l: r.mundo(c * cs + cs / 2, 256 - l * cs - cs / 2)       # noqa: E731
    r.arrastar(centro(0, 3), centro(4, 3), passos=12)        # arrastando: uma fileira de grama
    assert mapa.linhas[3][:5] == grama * 5
    arquivo = app.projeto.raiz / mapa.arquivo
    assert grama * 5 in arquivo.read_text(encoding="utf-8")   # salvo no .mapa sozinho
    r.clicar(*centro(2, 3), mods=("shift",))                 # Shift apaga
    assert mapa.linhas[3][2] == "."
    r.tecla("z", mods=("ctrl",))                             # Ctrl+Z desfaz o apagar
    assert mapa.linhas[3][2] == grama
    r.arrastar(r.item_projeto("bricks_brown.png"), paleta())  # segundo bloco
    tijolo = app.pincel
    r.clicar(*centro(1, 1))
    assert mapa.letra_na_celula(1, 1) == tijolo
    r.clicar(*centro(0, 3), mods=("ctrl",))                  # conta-gotas: volta para a grama
    assert app.pincel == grama
    r.clicar(*centro(-1, 3))                                 # pintar à esquerda aumenta o mapa
    assert mapa.linhas[3][:6] == grama * 6 and go.transform.x == -cs
    r.tecla("escape")
    assert app.pincel is None
    # o bloco escolhido na paleta pode deixar de ser sólido
    r.clicar(*next(rr.center for rr, l in app._quadros_paleta if l == tijolo))
    r.marcar("bloco_solido", False, "MapaTiles")
    assert not mapa.legenda[tijolo]["solido"]
    assert f"{tijolo} = Assets/Sprites/bricks_brown.png\n" in arquivo.read_text(encoding="utf-8")


@pytest.mark.gpu
def test_robo_clica_num_bloco_da_fase_e_edita(tmp_path):
    """No Pulo Verde: clicar num bloco da fase seleciona o mapa com esse bloco no pincel; pintar muda a fase."""
    import os
    os.environ["ENGINE2D_SEM_RECENTES"] = "1"
    from editor_visual.robo import RoboEditor
    proj = tmp_path / "Plat"
    shutil.copytree(RAIZ / "ProjetoPlataforma", proj, ignore=shutil.ignore_patterns("Library", "Saves", "__pycache__"))
    r = RoboEditor(proj)
    try:
        app = r.app
        app.abrir_cena(proj / "Assets/Cenas/Fase1.cena")
        r.quadros(3)
        mapa_go = app.cena.encontrar("Mapa")
        mapa = mapa_go.obter("MapaTiles")
        x0, y0 = mapa_go.transform.posicao_mundo
        app.cam.x, app.cam.y, app.cam.zoom = 300, 400, 0.6
        r.quadros(2)
        bloco = lambda c, l: r.mundo(x0 + c * 64 + 32, y0 - l * 64 - 32)        # noqa: E731
        r.clicar(*bloco(5, 9))                               # um bloco de grama do chão
        assert app.selecionado is mapa_go and app.pincel == "G"
        r.clicar(*bloco(5, 6))                               # pinta um bloco de grama no ar
        assert mapa.letra_na_celula(5, 6) == "G"
        texto = (proj / "Assets/Fases/fase1.mapa").read_text(encoding="utf-8")
        assert texto.splitlines()[texto.splitlines().index("---") + 1 + 6][5] == "G"
        assert "o = prefab Assets/Prefabs/moeda.prefab" in texto         # a legenda continua igual
    finally:
        r.fechar()


@pytest.mark.gpu
def test_robo_adiciona_luzes_e_liga_desliga_na_scene(robo):
    r, app = robo, robo.app
    r.menu("GameObject", "2D: Quadrado")
    r.adicionar_componente("Luz2D")                          # categoria "Luz" do Adicionar Componente
    r.preencher("tipo", "cone", "Luz2D")
    r.preencher("raio", "350", "Luz2D")
    r.marcar("sombras", True, "Luz2D")
    luz = app.selecionado.obter("Luz2D")
    assert (luz.tipo, luz.raio, luz.sombras) == ("cone", 350.0, True) and app.cena.luzes == [luz]
    assert app.cena.iluminacao()["pontos"][0]["cone"]
    r.adicionar_componente("ProjetorSombra2D")
    r.quadros(2)
    sv = app.r_scene
    r.clicar(sv.x + 125, sv.y + 11)                          # botão "Luzes" no alto da Scene
    assert app.ver_luzes is False
    r.clicar(sv.x + 125, sv.y + 11)
    assert app.ver_luzes is True


def test_textura_que_falta_vira_xadrez():
    pytest.importorskip("OpenGL")
    import pygame
    from engine2d import Motor
    m = Motor(64, 64, visivel=False, editor=False, vsync=False)
    try:
        t1 = m.texturas.carregar("")
        t2 = m.texturas.carregar("nao/existe.png")
        assert t1 is t2 and m.texturas.eh_sem_imagem(t1) and t1.largura == 32
    finally:
        pygame.quit()


@pytest.mark.gpu
def test_editor_fluxo_basico(tmp_path):
    import pygame
    from editor_visual.app import EditorApp
    proj = tmp_path / "Copia"
    shutil.copytree(RAIZ / "ProjetoExemplo", proj, ignore=shutil.ignore_patterns("Library", "__pycache__"))
    app = EditorApp(str(proj))
    app.layout()

    def quadros(n=2):
        for _ in range(n):
            app.motor.entrada.novo_quadro()
            pygame.event.pump()
            app.motor.entrada.mouse_tela = (5, 5)
            app.quadro()
    quadros()
    jog = app.cena.encontrar("jogador")
    app.selecionado = jog
    arq = app.projeto.criar_script(proj / "Assets/Scripts", "Girador")
    app.recarregar_scripts()
    app._adicionar_componente(jog, "Girador")
    quadros()
    assert jog.obter("Girador") is not None
    app.desfazer()
    assert app.cena.encontrar("jogador").obter("Girador") is None
    app.desfazer(refazer=True)
    assert app.cena.encontrar("jogador").obter("Girador") is not None
    app.salvar_prefab(app.cena.encontrar("jogador"), proj / "Assets/Prefabs")
    assert (proj / "Assets/Prefabs/jogador.prefab").exists()
    app.caminho_cena = proj / "Assets/Cenas/Principal.cena"
    app.salvar_cena()
    assert not app.modificado
    texto = (proj / "Assets/Cenas/Principal.cena").read_text(encoding="utf-8")
    assert "Girador" in texto and arq.exists()
    app.motor.encerrar()
