"""Testes das camadas de desenho, da física de plataforma, do mapa de tiles, da tela cheia e do
jogo de plataforma (ProjetoPlataforma) jogado por um robô até a bandeira."""
import os
import shutil
from pathlib import Path

import pytest

from conftest import TexturaFalsa
from engine2d import Cena, Colisor, CorpoRigido, ListaRenderizacao, Sprite

RAIZ = Path(__file__).resolve().parent.parent


# --- ordem de desenho -------------------------------------------------------------------------------
def test_ordem_camada_de_desenho_depois_ordem_depois_hierarquia():
    lista = ListaRenderizacao()
    tex = TexturaFalsa()

    def sp(nome, camada_desenho, ordem, hier):
        s = Sprite(tex, nome=nome, camada=ordem)
        s.indice_camada, s.ordem_hierarquia = camada_desenho, hier
        return lista.adicionar(s)

    sp("frente", 2, -50, 0)          # camada de desenho "Frente" ganha de qualquer ordem
    sp("b", 1, 0, 5)
    sp("a", 1, 0, 3)                 # mesma camada e ordem: quem vem antes na Hierarchy fica atrás
    sp("ordem_menor", 1, -1, 9)
    sp("fundo", 0, 99, 1)
    assert [s.nome for s in lista.ordenados()] == ["fundo", "ordem_menor", "a", "b", "frente"]


def test_numerar_e_reordenar_hierarquia():
    cena = Cena()
    a, b, c = (cena.criar(n) for n in "abc")
    filho = cena.criar("filho", pai=a)
    cena.numerar_hierarquia()
    assert [g.indice_hierarquia for g in (a, filho, b, c)] == [0, 1, 2, 3]
    cena.mover_na_hierarquia(c, None, 0)          # c vai para o topo
    cena.numerar_hierarquia()
    assert [g.nome for g in cena.raizes()] == ["c", "a", "b"] and c.indice_hierarquia == 0
    cena.mover_na_hierarquia(b, a, 0)             # b vira o primeiro filho de a
    cena.numerar_hierarquia()
    assert [f.nome for f in a.filhos] == ["b", "filho"] and b.indice_hierarquia == 2
    assert [o["nome"] for o in cena.para_dict()["objetos"]] == ["c", "a"]       # a ordem é salva


def test_objeto_oculto_nao_vai_para_a_cena_salva():
    cena = Cena()
    cena.criar("visivel")
    aux = cena.criar("auxiliar")
    aux.oculto = True
    assert [o["nome"] for o in cena.para_dict()["objetos"]] == ["visivel"]


def test_corpo_rigido_aceita_o_nome_antigo_cinematico():
    assert CorpoRigido(cinematico=True).tipo == "cinematico"
    assert CorpoRigido().tipo == "dinamico" and not CorpoRigido().cinematico


# --- física de plataforma ---------------------------------------------------------------------------
def _mundo():
    cena = Cena()
    cena.fisica.gravidade = (0.0, -1800.0)
    cena.criar("chao", 320, 20, componentes=[Colisor(forma="caixa", largura=640, altura=40)])
    cena.criar("parede", 500, 100, componentes=[Colisor(forma="caixa", largura=40, altura=160)])
    cena.criar("nuvem", 200, 160, componentes=[Colisor(forma="caixa", largura=120, altura=20, so_por_cima=True)])
    j = cena.criar("j", 100, 300, componentes=[CorpoRigido(), Colisor(forma="caixa", largura=40, altura=60)])
    return cena, j, j.obter(CorpoRigido)


def _rodar(cena, seg):
    for _ in range(int(seg * 60)):
        cena.atualizar(1 / 60)


def test_gravidade_chao_e_parede():
    cena, j, rb = _mundo()
    _rodar(cena, 1.0)
    assert abs(j.transform.y - 70) < 0.5 and rb.no_chao and rb.vy == 0      # parado em cima do chão
    for _ in range(120):
        rb.vx = 300
        cena.atualizar(1 / 60)
    assert abs(j.transform.x - 460) < 0.5 and rb.na_parede == 1 and rb.vx == 0


def test_plataforma_atravessavel_e_queda_rapida():
    cena, j, rb = _mundo()
    j.transform.x, j.transform.y = 200, 70
    _rodar(cena, 0.2)
    rb.vy = 900                                    # pula por baixo da nuvem
    _rodar(cena, 1.5)
    assert abs(j.transform.y - 200) < 0.5 and rb.no_chao           # passou e ficou em cima
    j.transform.x, j.transform.y = 100, 2000
    rb.vy = -3000                                  # caindo muito rápido não atravessa o chão
    _rodar(cena, 1.5)
    assert abs(j.transform.y - 70) < 0.5


def test_cinematico_nao_cai_e_estatico_nao_anda():
    cena = Cena()
    cena.fisica.gravidade = (0.0, -1800.0)
    k = cena.criar("k", 0, 100, componentes=[CorpoRigido(tipo="cinematico", vx=50)])
    e = cena.criar("e", 0, 100, componentes=[CorpoRigido(tipo="estatico", vx=50)])
    _rodar(cena, 1.0)
    assert k.transform.y == 100 and abs(k.transform.x - 50) < 1 and e.transform.x == 0


def test_raio():
    cena, j, rb = _mundo()
    cena.iniciar_pendentes()                       # os colisores entram na física ao iniciar
    acerto = cena.fisica.lancar_raio(100, 300, 0, -1, 1000, ignorar=j)
    assert acerto[0].gameobject.nome == "chao" and abs(acerto[1] - 260) < 1e-6
    assert cena.fisica.lancar_raio(100, 300, 0, 1, 1000, ignorar=j) is None
    circ = cena.criar("bola", 300, 300, componentes=[Colisor(raio=10)])
    cena.iniciar_pendentes()
    acerto = cena.fisica.lancar_raio(200, 300, 1, 0, 500)
    assert acerto[0].gameobject is circ and abs(acerto[1] - 90) < 1e-6


# --- com GPU (janela oculta) --------------------------------------------------------------------------
def _motor(pasta=RAIZ, tamanho=(320, 240), **kw):
    pytest.importorskip("OpenGL")
    from engine2d import Motor
    return Motor(*tamanho, visivel=False, editor=False, vsync=False, pasta_assets=pasta, **kw)


@pytest.mark.gpu
def test_sprites_padrao_e_camada_do_sprite_renderer():
    from engine2d import SpriteRenderer
    from engine2d.textura import FORMAS
    m = _motor()
    try:
        m.configurar_projeto({"camadas_desenho": ["Fundo", "Padrao", "Frente"]})
        cena = Cena()
        m.carregar_cena(cena)
        for forma, (w, h) in FORMAS.items():
            t = m.texturas.carregar("embutido:" + forma)
            assert (t.largura, t.altura) == (w, h) and not m.texturas.eh_sem_imagem(t)
        a = cena.criar("a", componentes=[SpriteRenderer(imagem="embutido:quadrado", camada_desenho="Frente")])
        b = cena.criar("b", componentes=[SpriteRenderer(imagem="embutido:circulo", ordem=50, virar_x=True)])
        m.passo(1 / 60)
        assert [s.nome for s in cena.lista.ordenados()] == ["b", "a"]
        assert b.obter(SpriteRenderer).sprite.transformacao.sx < 0          # virado
    finally:
        m.encerrar()


@pytest.mark.gpu
def test_iluminacao_2d_luz_ambiente_sombra_e_brilho(tmp_path):
    """Mede pixels da tela: perto da luz claro, longe escuro (ambiente), atrás do objeto sombra, e um
    sprite que não recebe luz mantém a cor."""
    from PIL import Image
    from engine2d import Luz2D, ProjetorSombra2D, SpriteRenderer
    m = _motor(tamanho=(400, 200))
    try:
        cena = Cena()
        m.carregar_cena(cena)
        cena.criar("chao", 200, 100, componentes=[SpriteRenderer(imagem="embutido:quadrado", largura=400, altura=200)])
        cena.criar("amb", componentes=[Luz2D(tipo="global", intensidade=0.2)])
        cena.criar("luz", 100, 100, componentes=[Luz2D(raio=300, intensidade=1.0, sombras=True)])
        cena.criar("bloco", 160, 100, componentes=[Colisor(forma="caixa", largura=20, altura=200), ProjetorSombra2D()])
        cena.criar("brilho", 380, 180, componentes=[SpriteRenderer(imagem="embutido:quadrado", largura=20, altura=20,
                                                                      cor=(1, 0, 0, 1), receber_luz=False)])
        m.passo(1 / 60)
        m.capturar_tela(str(tmp_path / "l.png"))
        m.passo(1 / 60)
        img = Image.open(tmp_path / "l.png").convert("RGB")
        brilho = lambda x, y: sum(img.getpixel((x, 199 - y))) / 3        # noqa: E731 (y para cima)
        assert brilho(105, 100) > 200                  # do lado da luz
        assert brilho(140, 100) > brilho(250, 100) + 60  # atrás do bloco ficou na sombra (só o ambiente)
        assert abs(brilho(250, 100) - 0.2 * 255) < 12   # na sombra sobra a luz ambiente (20%)
        assert img.getpixel((380, 199 - 180)) == (255, 0, 0)            # não recebe luz: cor pura
        assert m.renderizador.stats.luzes == 1 and m.renderizador.stats.sombras >= 2
        # cena sem nenhuma Luz2D: tudo com a cor normal
        for g in [g for g in cena.objetos if g.obter(Luz2D)]:
            g.destruir()
        m.passo(1 / 60)
        m.capturar_tela(str(tmp_path / "s.png"))
        m.passo(1 / 60)
        assert sum(Image.open(tmp_path / "s.png").convert("RGB").getpixel((250, 100))) / 3 > 250
    finally:
        m.encerrar()


@pytest.mark.gpu
def test_painel_f3_e_tremor_de_camera():
    import pygame
    m = _motor()
    try:
        cena = Cena()
        m.carregar_cena(cena)
        m.entrada.processar(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F3, mod=0, unicode="", scancode=0))
        m.passo(1 / 60)
        assert m.mostrar_estatisticas                         # F3 liga o painel
        m.entrada.novo_quadro()
        m.tremer(10, 0.5)
        x0 = m.camera.x
        desloc = [m._deslocamento_tremor(0.1) for _ in range(3)]
        assert any(abs(dx) > 0 for dx, _ in desloc) and m.camera.x == x0   # treme sem mexer na câmera
        for _ in range(10):
            m._deslocamento_tremor(0.1)
        assert m._deslocamento_tremor(0.1) == (0.0, 0.0)       # e para sozinho
    finally:
        m.encerrar()


@pytest.mark.gpu
def test_luz_que_apaga_e_cone(tmp_path):
    from engine2d import Luz2D
    m = _motor()
    try:
        cena = Cena()
        m.carregar_cena(cena)
        flash = cena.criar("flash", 0, 0, componentes=[Luz2D(intensidade=2.0, apagar_em=0.5)]).obter(Luz2D)
        cone = cena.criar("farol", 0, 0, rotacao=30, componentes=[Luz2D(tipo="cone", angulo=90, abertura=40)]).obter(Luz2D)
        m.passo(0.25)
        assert 0.9 < flash.intensidade_atual() < 1.1
        assert cone.dados()["cone"] == (120.0, 40.0)                       # direção soma a rotação do objeto
        for _ in range(3):
            m.passo(0.25)
        assert not flash.habilitado and all(d.get("cone") for d in cena.iluminacao()["pontos"])
    finally:
        m.encerrar()


@pytest.mark.gpu
def test_tela_cheia_amplia_e_converte_o_mouse(tmp_path):
    import pygame
    m = _motor(tamanho=(480, 270), tela_cheia=True)
    try:
        assert m._fbo is not None
        cena = Cena()
        m.carregar_cena(cena)
        m.passo(1 / 60)
        m.capturar_tela(str(tmp_path / "t.png"))
        m.passo(1 / 60)
        from PIL import Image
        assert Image.open(tmp_path / "t.png").size == (480, 270)       # captura na resolução do jogo
        jw, jh = m.tamanho_janela
        x0, y0, w, h = m._area_tela
        m.entrada.processar(pygame.event.Event(pygame.MOUSEMOTION, pos=(x0 + w // 2, y0 + h // 2), rel=(0, 0),
                                               buttons=(0, 0, 0)))
        mx, my = m.entrada.mouse_tela
        assert abs(mx - 240) < 1 and abs(my - 135) < 1
    finally:
        m.encerrar()


@pytest.mark.gpu
def test_mapa_de_tiles_junta_colisores_e_cria_prefabs(tmp_path):
    from engine2d import MapaTiles
    prefab = tmp_path / "moeda.prefab"
    prefab.write_text('{"nome": "moeda", "componentes": [{"tipo": "SpriteRenderer", "campos": '
                      '{"imagem": "embutido:circulo"}}]}', encoding="utf-8")
    mapa = tmp_path / "t.mapa"
    mapa.write_text(f"G = embutido:quadrado solido\nn = embutido:losango so_por_cima\no = prefab {prefab.as_posix()}\n"
                    "---\n....o.....\n....nnn...\n..........\nGGGG..GGGG\nGGGGGGGGGG\n", encoding="utf-8")
    m = _motor()
    try:
        cena = Cena()
        m.carregar_cena(cena)
        go = cena.criar("mapa", 0, 320, componentes=[MapaTiles(arquivo=str(mapa), tamanho_celula=32)])
        m.passo(1 / 60)
        mt = go.obter(MapaTiles)
        colisores = [g for g in cena.objetos if g.oculto]
        assert len(mt._celulas) == 21 and len(colisores) == 4
        assert any(g.obter(Colisor).so_por_cima for g in colisores)
        moedas = [g for g in cena.objetos if g.nome == "moeda"]
        assert len(moedas) == 1 and moedas[0].transform.x == 4 * 32 + 16
        assert mt.solido_em(16, 320 - 32 * 3 - 16) and not mt.solido_em(16 * 9, 320 - 16)
        assert (mt.largura_mundo, mt.altura_mundo) == (320, 160)
    finally:
        m.encerrar()


@pytest.mark.gpu
def test_plataforma_jogada_ate_a_bandeira(tmp_path):
    """O robô anda para a direita e pula quando vê buraco, parede ou inimigo (usando o raio da física)."""
    import pygame
    import agentdsl.componente  # noqa: F401
    from engine2d.projeto import Projeto
    raiz = tmp_path / "Plataforma"
    shutil.copytree(RAIZ / "ProjetoPlataforma", raiz, ignore=shutil.ignore_patterns("Library", "Saves", "__pycache__"))
    cwd = os.getcwd()
    proj = Projeto(raiz)
    try:
        os.chdir(raiz)
        proj.carregar_scripts()
        assert not proj.erros_scripts, proj.erros_scripts
        m = _motor(raiz, (proj.largura, proj.altura))
        m.configurar_projeto(proj.configuracoes())
        cena = Cena("Menu")
        cena.carregar(proj.cena_inicial)
        m.carregar_cena(cena)

        def tecla(nome, baixo=True):
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN if baixo else pygame.KEYUP,
                                                 key=pygame.key.key_code(nome), mod=0, unicode="", scancode=0))

        def quadro():
            m.entrada.novo_quadro()
            for ev in pygame.event.get():
                m.entrada.processar(ev)
            m.passo(1 / 60)
            m.quadro += 1

        for _ in range(5):
            quadro()
        tecla("space")
        for _ in range(3):
            quadro()
        tecla("space", False)
        quadro()
        assert m.cena.nome == "Fase1"
        import Plataforma as P
        tecla("right")
        segurar, pisoes, blocos = 0, 0, set()
        for _ in range(120 * 60):
            quadro()
            j, h = P.jogador(m.cena), P.hud(m.cena)
            j.vidas = max(j.vidas, 3)
            if h.estado == "vitoria":
                break
            col = j.obter("Colisor")
            x0, y0, x1, y1 = col.aabb()
            f = m.cena.fisica
            buraco = f.lancar_raio(x1 + 22, y0 + 2, 0, -1, 200, ignorar=j.gameobject) is None
            parede = f.lancar_raio(x1, y0 + 20, 1, 0, 40, ignorar=j.gameobject, camada="chao") is not None
            x, y = j.transform.posicao_mundo
            inimigo = any(0 < g.transform.x - x < 190 and abs(g.transform.y - y) < 90 and not g.obter("Inimigo").morto
                          for g in m.cena.com_tag("inimigo") if g.obter("Inimigo"))
            if segurar > 0:
                segurar -= 1
                if segurar == 0:
                    tecla("space", False)
            elif j.rb.no_chao and (buraco or parede or inimigo):
                tecla("space")
                segurar = 22
        h = P.hud(m.cena)
        assert h.estado == "vitoria", (h.estado, P.jogador(m.cena).transform.x)
        assert h.moedas >= 5 and h.pontos > 1000
        fase = m.cena.servicos["agentes"].sis.agentes["fase"]
        assert any(c[0] == "moedas" for c in fase.crencas)               # o agente "fase" recebeu as moedas
        assert m.erro_atual is None
        m.encerrar()
    finally:
        proj.descarregar()
        os.chdir(cwd)
