"""Testes funcionais da engine (sem GPU): transformações, camadas e seleção."""
import math

import numpy as np
import pytest

from conftest import TexturaFalsa
from engine2d import Camera2D, Cena, Sprite, Transformacao
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
    cena = Cena()
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
    cena = Cena(agrupar_texturas=True)
    t1, t2 = TexturaFalsa(id_=1), TexturaFalsa(id_=2)
    for i, (tex, cam) in enumerate([(t2, 1), (t1, 1), (t2, 0), (t1, 0)]):
        cena.adicionar(Sprite(tex, camada=cam, nome=str(i)))
    ordem = cena.ordenados()
    assert [s.camada for s in ordem] == [0, 0, 1, 1]
    assert [s.textura.id for s in ordem] == [1, 2, 1, 2]


def test_selecao_respeita_rotacao_e_camada():
    cena = Cena()
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


@pytest.mark.gpu
def test_demo_roda_alguns_quadros():
    pytest.importorskip("OpenGL")
    import demo_engine
    demo_engine.main(max_quadros=5)
