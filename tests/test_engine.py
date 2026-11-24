"""Testes funcionais da engine (sem GPU): transformações, camadas, seleção, GameObjects e física."""
import math
from pathlib import Path

import numpy as np
import pytest

from conftest import TexturaFalsa
from engine2d import (Camera2D, Cena, Colisor, Componente, CorpoRigido, GameObject, ListaRenderizacao,
                      Sprite, Transformacao)
from engine2d import matematica as M


def test_modelo_igual_a_produto_T_R_S():
    for (tx, ty, th, sx, sy) in [(0, 0, 0, 1, 1), (10, -5, 30, 2, 0.5), (-3, 7, 270, 1.5, 3)]:
        esperado = M.translacao(tx, ty) @ M.rotacao(th) @ M.escala(sx, sy)
        assert np.allclose(M.modelo(tx, ty, th, sx, sy), esperado, atol=1e-5)


def test_ordem_das_transformacoes_importa():
    # T·R·S ≠ S·R·T: escala aplicada primeiro, translação por último.
    a = M.translacao(10, 0) @ M.rotacao(90) @ M.escala(2, 1)
    b = M.escala(2, 1) @ M.rotacao(90) @ M.translacao(10, 0)
    assert not np.allclose(a, b)
    # vértice (1, 0): escala → (2, 0); rotação 90° → (0, 2); translação → (10, 2)
    assert np.allclose(M.aplicar(a, 1, 0), (10, 2), atol=1e-5)


def test_modelo_vetorizado_confere_com_escalar():
    rng = np.random.default_rng(0)
    vals = [rng.uniform(-100, 100, 50) for _ in range(5)]
    vet = M.modelo_vetorizado(*vals)
    for i in range(50):
        assert np.allclose(vet[i], M.modelo(*(v[i] for v in vals)), atol=1e-4)


def test_ortografica_leva_cantos_para_ndc():
    p = M.ortografica(0, 800, 0, 600)
    assert np.allclose(M.aplicar(p, 0, 0), (-1, -1))
    assert np.allclose(M.aplicar(p, 800, 600), (1, 1))
    assert np.allclose(M.aplicar(p, 400, 300), (0, 0))


def test_transformacao_cache_e_operacoes():
    t = Transformacao(5, 5)
    m1 = t.matriz()
    assert t.matriz() is m1            # não recalcula sem mudança
    t.transladar(5, -5)
    t.rotacionar(370)
    t.escalar(2)
    assert (t.x, t.y) == (10, 0)
    assert math.isclose(t.rotacao, 10)
    assert (t.sx, t.sy) == (2, 2)
    assert t.matriz() is not m1


def test_camadas_menores_desenhadas_primeiro_e_ordem_estavel():
    cena = ListaRenderizacao()
    tex = TexturaFalsa()
    a = cena.adicionar(Sprite(tex, camada=2, nome="a"))
    b = cena.adicionar(Sprite(tex, camada=0, nome="b"))
    c = cena.adicionar(Sprite(tex, camada=2, nome="c"))
    d = cena.adicionar(Sprite(tex, camada=1, nome="d"))
    assert [s.nome for s in cena.ordenados()] == ["b", "d", "a", "c"]
    n = cena.ordenacoes
    cena.ordenados()
    assert cena.ordenacoes == n        # sem mudanças, não reordena
    b.camada = 5                       # mudar a camada invalida a ordem
    assert [s.nome for s in cena.ordenados()] == ["d", "a", "c", "b"]
    cena.remover(a)
    assert [s.nome for s in cena.ordenados()] == ["d", "c", "b"]


def test_agrupar_texturas_mantem_ordem_entre_camadas():
    cena = ListaRenderizacao(agrupar_texturas=True)
    t1, t2 = TexturaFalsa(id_=1), TexturaFalsa(id_=2)
    for i, (tex, cam) in enumerate([(t2, 1), (t1, 1), (t2, 0), (t1, 0)]):
        cena.adicionar(Sprite(tex, camada=cam, nome=str(i)))
    ordem = cena.ordenados()
    assert [s.camada for s in ordem] == [0, 0, 1, 1]
    assert [s.textura.id for s in ordem] == [1, 2, 1, 2]


def test_selecao_respeita_rotacao_e_camada():
    cena = ListaRenderizacao()
    tex = TexturaFalsa(100, 20)
    fundo = cena.adicionar(Sprite(tex, x=0, y=0, camada=0, nome="fundo"))
    frente = cena.adicionar(Sprite(tex, x=0, y=0, camada=3, rotacao=90, nome="frente"))
    # Girado 90°, "frente" ocupa 20 de largura x 100 de altura.
    assert frente.contem_ponto(0, 40) and not frente.contem_ponto(40, 0)
    assert cena.sprite_em(0, 40) is frente
    assert cena.sprite_em(40, 0) is fundo
    assert cena.sprite_em(500, 500) is None


def test_camera_tela_para_mundo():
    cam = Camera2D(800, 600)
    cam.x, cam.y, cam.zoom = 100, 50, 2
    # O centro da tela mostra (cam.x, cam.y)
    assert np.allclose(cam.tela_para_mundo(400, 300), (100, 50))
    # 100 px à direita na tela = 50 unidades no mundo com zoom 2
    assert np.allclose(cam.tela_para_mundo(500, 300), (150, 50))


# ---------------------------------------------------------------- GameObject / Transform
def test_hierarquia_compoe_poses():
    pai = GameObject("pai", x=100, y=50, rotacao=90, escala=2)
    filho = GameObject("filho", x=10, y=0, pai=pai)
    x, y, r, sx, sy = filho.transform.mundo()
    # (10, 0) escalado por 2 → (20, 0); girado 90° → (0, 20); somado ao pai → (100, 70)
    assert np.allclose((x, y, r, sx), (100, 70, 90, 2), atol=1e-6)
    filho.transform.posicao_mundo = (0, 0)          # definir no mundo ajusta o local
    assert np.allclose(filho.transform.posicao_mundo, (0, 0), atol=1e-6)
    with pytest.raises(ValueError):
        pai.transform.definir_pai(filho.transform)    # ciclo


def test_ciclo_de_vida_dos_componentes():
    eventos = []

    class Registro(Componente):
        def iniciar(self):
            eventos.append("iniciar")

        def atualizar(self, dt):
            eventos.append("atualizar")

        def atualizar_tardio(self, dt):
            eventos.append("tardio")

        def ao_destruir(self):
            eventos.append("destruir")

    cena = Cena()
    go = cena.criar("x", componentes=[Registro()])
    cena.atualizar(0.1)
    cena.atualizar(0.1)
    go.destruir()
    assert go in cena.objetos            # Destroy acontece no fim do quadro
    cena.atualizar(0.1)
    assert eventos == ["iniciar", "atualizar", "tardio", "atualizar", "tardio", "atualizar", "tardio", "destruir"]
    assert go not in cena.objetos and go.destruido


def test_destruir_pai_destroi_filhos_e_encontrar():
    cena = Cena()
    pai = cena.criar("pai")
    filho = cena.criar("filho", pai=pai)
    assert cena.encontrar("filho") is filho
    pai.destruir()
    cena.atualizar(0)
    assert filho.destruido and cena.encontrar("filho") is None


def test_fisica_separa_corpos_e_dispara_eventos():
    entradas = []

    class Ouvinte(Componente):
        def ao_entrar_colisao(self, outro):
            entradas.append(outro.gameobject.nome)

    cena = Cena()
    a = cena.criar("a", 0, 0, componentes=[CorpoRigido(), Colisor(raio=10), Ouvinte()])
    cena.criar("parede", 12, 0, componentes=[Colisor(forma="caixa", largura=10, altura=40)])
    cena.criar("sensor", -5, 0, componentes=[Colisor(raio=4, gatilho=True)])
    cena.atualizar(1 / 60)
    assert sorted(entradas) == ["parede", "sensor"]
    # círculo (raio 10) invade 3 px a parede (borda em x=7); a parede é estática,
    # então só o corpo dinâmico é empurrado: o centro vai para x = -3. O gatilho não empurra.
    assert abs(a.transform.x - (-3)) < 1e-6
    entradas.clear()
    cena.atualizar(1 / 60)
    assert entradas == []                 # "entrar" só no primeiro contato


def test_camadas_de_colisao_e_consultas():
    cena = Cena()
    cena.fisica.ignorar("tiro", "tiro")
    for k in range(3):
        cena.criar(f"t{k}", 0, 0, componentes=[Colisor(raio=5, camada_fisica="tiro", gatilho=True)])
    cena.criar("alvo", 100, 0, componentes=[Colisor(raio=5, camada_fisica="inimigo")])
    cena.atualizar(0)
    assert cena.fisica.contatos_quadro == 0
    assert [c.gameobject.nome for c in cena.fisica.consultar_circulo(95, 0, 2, "inimigo")] == ["alvo"]
    assert cena.fisica.mais_proximo(0, 0, "inimigo").gameobject.nome == "alvo"


def test_cena_json_e_prefab():
    cena = Cena()
    pai = cena.criar("pai", 5, 6, componentes=[CorpoRigido(vx=3)])
    cena.criar("filho", 1, 2, pai=pai, componentes=[Colisor(raio=7, gatilho=True)])
    dados = cena.para_dict()
    nova = Cena()
    nova.carregar_dict(dados)
    p2 = nova.encontrar("pai")
    assert p2.obter(CorpoRigido).vx == 3 and p2.transform.x == 5
    f2 = nova.encontrar("filho")
    assert f2.pai is p2 and f2.obter(Colisor).raio == 7 and f2.obter(Colisor).gatilho
    nova.registrar_prefab("bala", {"nome": "bala", "componentes": [{"tipo": "CorpoRigido", "campos": {"vx": 1}}]})
    b = nova.instanciar("bala", 10, 20, CorpoRigido__vx=9)
    assert (b.transform.x, b.transform.y, b.obter(CorpoRigido).vx) == (10, 20, 9)


def test_campos_invalidos_sao_recusados():
    with pytest.raises(TypeError):
        Colisor(raiio=3)


@pytest.mark.gpu
def test_demo_roda_alguns_quadros():
    pytest.importorskip("OpenGL")
    import demo_engine
    demo_engine.main(max_quadros=5)


@pytest.mark.gpu
@pytest.mark.parametrize("projeto", ["ProjetoArena", "ProjetoTorres", "ProjetoSorveteria", "ProjetoNavinha",
                                     "ProjetoPlataforma"])
def test_jogos_rodam_alguns_quadros(projeto):
    pytest.importorskip("OpenGL")
    import os
    import rodar
    cwd = os.getcwd()
    try:
        assert rodar.main([str(Path(__file__).resolve().parent.parent / projeto)], max_quadros=30) == 0
    finally:
        os.chdir(cwd)


def _motor_oculto(pasta=None, tamanho=(320, 240)):
    from engine2d import Motor
    return Motor(*tamanho, visivel=False, editor=False, vsync=False, pasta_assets=pasta)


@pytest.mark.gpu
def test_particulas_nascem_andam_e_somem():
    pytest.importorskip("OpenGL")
    from engine2d import EmissorParticulas
    m = _motor_oculto(Path(__file__).resolve().parent.parent)
    try:
        cena = Cena()
        m.carregar_cena(cena)
        go = cena.criar("boom", 100, 100, componentes=[
            EmissorParticulas(imagem="assets/estrela.png", rajada=20, taxa=0, emitindo=False, vida=0.3,
                              vida_variacao=0, destruir_ao_fim=True, area_largura=40)])
        m.passo(1 / 60)
        em = go.obter(EmissorParticulas)
        assert em.quantidade == 20 and len(cena.lista) == 20
        xs = {round(p[0].x) for p in em._vivas}
        assert len(xs) > 5                       # nasceram espalhadas na área de 40 px
        for _ in range(30):
            m.passo(1 / 60)
        assert em.quantidade == 0 and go.destruido and len(cena.lista) == 0
        # emissor desligado: as partículas somem em vez de congelar na tela
        go2 = cena.criar("fogo", 0, 0, componentes=[EmissorParticulas(imagem="assets/estrela.png", taxa=60)])
        for _ in range(10):
            m.passo(1 / 60)
        assert go2.obter(EmissorParticulas).quantidade > 0
        go2.ativo = False
        m.passo(1 / 60)
        assert go2.obter(EmissorParticulas).quantidade == 0 and len(cena.lista) == 0
    finally:
        m.encerrar()


@pytest.mark.gpu
def test_fundo_rolante_cobre_a_area_e_rola():
    pytest.importorskip("OpenGL")
    from engine2d import FundoRolante
    m = _motor_oculto(Path(__file__).resolve().parent.parent)
    try:
        cena = Cena()
        m.carregar_cena(cena)
        go = cena.criar("fundo", 160, 120, componentes=[
            FundoRolante(imagem="assets/estrela.png", velocidade_y=-100, largura=320, altura=240)])
        m.passo(1 / 60)
        f = go.obter(FundoRolante)
        cols, linhas, tw, th = f._grade
        assert cols * tw >= 320 + tw and linhas * th >= 240 + th
        y0 = min(sp.y for sp in f._sprites)
        m.passo(0.1)
        assert min(sp.y for sp in f._sprites) != y0                # rolou
        xs = [sp.x - sp.largura / 2 for sp in f._sprites]
        assert min(xs) <= 0 and max(sp.x + sp.largura / 2 for sp in f._sprites) >= 320   # cobre a tela
    finally:
        m.encerrar()


@pytest.mark.gpu
def test_trocar_cena_pelo_arquivo_e_reiniciar(tmp_path):
    pytest.importorskip("OpenGL")
    a = tmp_path / "a.cena"
    b = tmp_path / "b.cena"
    for arq in (a, b):
        c = Cena(arq.stem)
        c.criar(f"obj_{arq.stem}")
        c.salvar(arq)
    m = _motor_oculto()
    try:
        cena = Cena()
        cena.carregar(a)
        m.carregar_cena(cena)
        m.trocar_cena(str(b))
        m.passo(1 / 60)
        assert m.cena.nome == "b" and m.cena.encontrar("obj_b") is not None
        m.cena.criar("extra")
        m.reiniciar_cena()
        m.passo(1 / 60)
        assert m.cena.nome == "b" and m.cena.encontrar("extra") is None
        assert m.audio.ok is False          # janela oculta = sem som (e sem erro ao tocar)
        m.audio.tocar("nao_existe.ogg")
    finally:
        m.encerrar()


@pytest.mark.gpu
def test_navinha_jogada_ate_a_vitoria(tmp_path):
    """Joga a navinha com teclas simuladas: menu → fase → 6 ondas da DSL → chefe → vitória."""
    pytest.importorskip("OpenGL")
    import os
    import shutil
    import pygame
    import agentdsl.componente  # noqa: F401
    from engine2d.projeto import Projeto
    raiz = tmp_path / "Navinha"         # numa cópia: o recorde de quem joga não é mexido
    shutil.copytree(Path(__file__).resolve().parent.parent / "ProjetoNavinha", raiz,
                    ignore=shutil.ignore_patterns("Library", "Saves", "__pycache__"))
    cwd = os.getcwd()
    proj = Projeto(raiz)
    try:
        os.chdir(raiz)
        proj.carregar_scripts()
        assert not proj.erros_scripts, proj.erros_scripts
        m = _motor_oculto(raiz, (proj.largura, proj.altura))
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

        for _ in range(10):
            quadro()
        tecla("space")
        for _ in range(3):              # a troca de cena acontece no começo do quadro seguinte
            quadro()
        tecla("space", False)
        quadro()
        tecla("space")                  # segura o tiro na fase
        assert m.cena.nome == "Fase1"
        import Navinha as N
        lado = "right"
        tecla(lado)
        ondas = set()
        for _ in range(170 * 60):
            quadro()
            j = N.jogador(m.cena)
            if j.transform.x > 650 and lado == "right":
                tecla("right", False); lado = "left"; tecla("left")       # noqa: E702
            elif j.transform.x < 250 and lado == "left":
                tecla("left", False); lado = "right"; tecla("right")      # noqa: E702
            j.vidas = max(j.vidas, 2)
            diretor = m.cena.servicos["agentes"].sis.agentes["diretor"]
            ondas |= {a[0] for _, a in diretor.crencas_com("onda", 1)}
            if N.hud(m.cena).estado == "vitoria":
                break
        h = N.hud(m.cena)
        assert h.estado == "vitoria", (sorted(ondas), h.pontos)
        assert set(range(1, 8)) <= ondas and h.pontos > 5000
        assert m.erro_atual is None
        m.encerrar()
    finally:
        proj.descarregar()
        os.chdir(cwd)


@pytest.mark.gpu
def test_sorveteria_do_zero(tmp_path):
    """Fábrica vazia -> tutorial -> primeiro sorvete; recurso bloqueado e erro comum com mensagem amigável."""
    pytest.importorskip("OpenGL")
    import os
    import random
    import shutil
    import agentdsl.componente  # noqa: F401
    from engine2d import Cena, Motor
    from engine2d.projeto import Projeto
    random.seed(1)
    origem = Path(__file__).resolve().parent.parent / "ProjetoSorveteria"
    raiz = tmp_path / "Sorveteria"
    shutil.copytree(origem, raiz, ignore=shutil.ignore_patterns("Library", "Saves", "__pycache__"))
    cwd = os.getcwd()
    proj = Projeto(raiz)
    try:
        os.chdir(raiz)
        proj.carregar_scripts()
        assert not proj.erros_scripts, proj.erros_scripts
        motor = Motor(1280, 720, "t", pasta_assets=raiz, editor=False, visivel=False, vsync=False)
        cena = Cena("Principal")
        cena.carregar(proj.cena_inicial)
        motor.carregar_cena(cena)

        def rodar(seg):
            for _ in range(int(seg * 60)):
                motor.entrada.novo_quadro()
                motor.passo(1 / 60)
                motor.quadro += 1

        rodar(0.1)
        fab, painel, tut = (cena.servicos[k] for k in ("sorveteria", "painel", "tutorial"))
        assert painel.tela == "inicio" and len(fab.robos()) == 1 and not fab.tem_estacao("maquina")
        painel._comecar()
        jan = painel.codigos()[0]

        def executar(texto):
            jan.editor.definir_texto(texto)
            return painel.executar(jan)

        # erros comuns viram mensagens de iniciante
        assert not executar("+!comecar <- pegar_casquinha, dancar.")
        assert "';'" in jan.erros[0][1]
        assert not executar("+!comecar <- pegar_casqinha.")
        assert "pegar_casquinha" in jan.erros[0][2]
        assert not executar("+!comecar : livre <- dancar.")
        assert "Sentidos" in jan.erros[0][1]
        # autocompletar: digitar "peg" sugere pegar_casquinha
        jan.editor.definir_texto("+!comecar <- ")
        jan.editor.lin, jan.editor.col = 0, len(jan.editor.linhas[0])
        jan.editor.fonte_sugestoes = painel._sugestoes
        jan.editor.focado = True
        for c in "peg":
            jan.editor._inserir(c)
        jan.editor._atualizar_sugestoes()
        assert jan.editor.sugestoes and jan.editor.sugestoes[0][0] == "pegar_casquinha("
        jan.editor._aceitar_sugestao()
        assert jan.editor.texto.startswith("+!comecar <- pegar_casquinha")
        # tutorial lento: a máquina e os clientes só aparecem depois de vários passos
        from Tutorial import PASSOS
        tut.avancar()
        motor.escala_tempo = 2
        for n in range(1, 16):
            if n == 11:                  # a máquina só chega ao entrar no passo 12
                assert not fab.tem_estacao("maquina")
            if n == 13:                  # o balcão e os clientes só no passo 14
                assert not fab.tem_estacao("balcao") and not fab.clientes
            if n == 3:                   # o que o robô fez continua valendo: ainda segura a casquinha
                assert fab.robos()[0].obter("Robo").item is not None
            codigo = PASSOS[n]["codigo"]
            assert executar(codigo), (n, jan.erros)
            for _ in range(180):
                if tut.passo > n:
                    break
                rodar(0.5)
            assert tut.passo > n, f"o passo {n} ({PASSOS[n]['titulo']}) não avançou"
        assert fab.tem_estacao("maquina") and fab.tem_estacao("balcao") and fab.vendidos >= 4
        # missões: escolher o sabor pelo pedido e dividir o trabalho entre dois robôs
        from Janelas import JanelaCodigo
        from Tutorial import MISSOES
        for chave in ("sentidos", "variaveis", "tipo_chocolate"):
            fab.dinheiro += 500
            assert fab.comprar(chave)[0], chave
        painel.tela = None
        rodar(0.5)                                       # o passo "A Árvore" vê Sentidos comprado
        assert tut.passo == len(PASSOS) - 1
        tut.avancar()                                    # "Pronto, a fábrica é sua!"

        def fazer_missao(chave):
            """Joga a missão com o código que ela mesma sugere (cada passo tem que avançar)."""
            assert tut.em_missao and tut.missoes[0][0] == chave, tut.missoes
            for k, p in enumerate(MISSOES[chave]):
                if p["cond"] is None:
                    tut.avancar()                        # passo só de explicação (botão)
                    continue
                assert executar(p["codigo"]), (chave, k, jan.erros)
                for _ in range(240):
                    if not tut.missoes or tut.missoes[0][0] != chave or tut.missoes[0][1] > k:
                        break
                    rodar(0.5)
                else:
                    raise AssertionError(f"missão {chave} passo {k} não avançou")

        # as compras de linguagem também ensinam: cada uma abre uma missão com um programa para testar
        fazer_missao("sentidos")
        fazer_missao("variaveis")
        assert tut.em_missao and tut.missoes[0][0] == "tipo_chocolate"
        assert executar(MISSOES["tipo_chocolate"][0]["codigo"]), jan.erros
        for _ in range(240):
            if tut.missoes and tut.missoes[0][1] > 0:
                break
            rodar(0.5)
        assert fab.vendas_tipo.get("chocolate", 0) >= 1
        tut.avancar()                                    # "Sabor certo!"
        for chave in ("operadores", "memoria", "relogio"):
            fab.dinheiro += 500
            assert fab.comprar(chave)[0], chave
            painel.tela = None
            fazer_missao(chave)
        assert not tut.missoes and {"sentidos", "variaveis", "operadores", "memoria", "relogio"} <= tut.feitas
        fab.dinheiro += 500
        assert fab.comprar("robos")[0] and len(fab.robos()) == 2
        painel.tela = None
        rodar(0.5)
        painel.nova_janela()
        j2 = painel.codigos()[-1]
        assert j2.alvo == "robo2"
        rodar(0.5)
        atender, montar = MISSOES["robos"][1]["codigo"].split("// janela do robo2 (monta)")
        jan.editor.definir_texto(atender)
        j2.editor.definir_texto(montar)
        assert painel.executar(jan) and painel.executar(j2), (jan.erros, j2.erros)
        for _ in range(240):
            if fab.vendas_robo.get("robo2", 0) >= 1 and fab.pedidos_passados >= 1:
                break
            rodar(0.5)
        assert fab.pedidos_passados >= 1 and fab.vendas_robo.get("robo2", 0) >= 1
        assert (raiz / "Saves/progresso.json").exists()
        motor.encerrar()
    finally:
        proj.descarregar()
        os.chdir(cwd)
