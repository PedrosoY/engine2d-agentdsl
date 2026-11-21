"""Testes funcionais da engine (sem GPU): transformações, camadas, seleção, GameObjects e física."""
import math

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
@pytest.mark.parametrize("jogo", ["arena", "torres"])
def test_jogos_rodam_alguns_quadros(jogo):
    pytest.importorskip("OpenGL")
    import jogar
    jogar.main([jogo], max_quadros=30)
