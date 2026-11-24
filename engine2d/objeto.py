"""Modelo de objetos: GameObject + Transform + Componentes.

- ``GameObject``: entidade da cena (nome, tag, ativo). Não tem comportamento
  próprio: tudo vem dos componentes anexados.
- ``Transform``: posição, rotação e escala LOCAIS, relativas ao pai. A pose no
  mundo é a composição com a pose de todos os ancestrais (hierarquia de cena):
      M_mundo(filho) = M_mundo(pai) · M_local(filho)
- ``Componente``: classe base dos comportamentos.
  Ganchos: iniciar() (antes do primeiro quadro), atualizar(dt) (todo quadro),
  atualizar_tardio(dt) (depois de todos os atualizar), ao_entrar_colisao(outro),
  ao_sair_colisao(outro), desenhar_ui(ui) (interface na tela) e ao_destruir().
  ``CAMPOS`` lista os atributos editáveis no inspector e salvos no JSON da cena.
"""
from __future__ import annotations

import itertools
import math

_ids = itertools.count(1)

# Registro de tipos de componente por nome (para carregar cenas/prefabs de JSON).
REGISTRO_COMPONENTES: dict[str, type] = {}


class Transform:
    __slots__ = ("x", "y", "rotacao", "escala_x", "escala_y", "pai", "filhos", "gameobject")

    def __init__(self, gameobject, x=0.0, y=0.0, rotacao=0.0, escala_x=1.0, escala_y=1.0):
        self.gameobject = gameobject
        self.x, self.y = float(x), float(y)
        self.rotacao = float(rotacao)
        self.escala_x, self.escala_y = float(escala_x), float(escala_y)
        self.pai: Transform | None = None
        self.filhos: list[Transform] = []

    # --- hierarquia ----------------------------------------------------------
    def definir_pai(self, pai: "Transform | None", manter_mundo: bool = False) -> None:
        if pai is self.pai:
            return
        p = pai
        while p is not None:                 # impede ciclos (pai dentro do próprio filho)
            if p is self:
                raise ValueError("um objeto não pode ser filho de si mesmo ou de um descendente")
            p = p.pai
        mundo = self.mundo() if manter_mundo else None
        if self.pai is not None:
            self.pai.filhos.remove(self)
        self.pai = pai
        if pai is not None:
            pai.filhos.append(self)
        if mundo:
            self.definir_mundo(*mundo)

    # --- composição de poses (pai ∘ local) -------------------------------------
    def mundo(self) -> tuple[float, float, float, float, float]:
        """(x, y, rotação, escala_x, escala_y) no espaço do mundo."""
        if self.pai is None:
            return self.x, self.y, self.rotacao, self.escala_x, self.escala_y
        px, py, pr, psx, psy = self.pai.mundo()
        c, s = math.cos(math.radians(pr)), math.sin(math.radians(pr))
        lx, ly = self.x * psx, self.y * psy
        return (px + lx * c - ly * s, py + lx * s + ly * c,
                pr + self.rotacao, psx * self.escala_x, psy * self.escala_y)

    @property
    def posicao_mundo(self) -> tuple[float, float]:
        m = self.mundo()
        return m[0], m[1]

    @posicao_mundo.setter
    def posicao_mundo(self, p) -> None:
        self.definir_mundo(p[0], p[1])

    def definir_mundo(self, x, y, rotacao=None, escala_x=None, escala_y=None) -> None:
        """Ajusta os valores locais para que a pose no MUNDO seja a pedida."""
        if self.pai is None:
            self.x, self.y = float(x), float(y)
            if rotacao is not None:
                self.rotacao = rotacao
            if escala_x is not None:
                self.escala_x, self.escala_y = escala_x, escala_y if escala_y is not None else escala_x
            return
        px, py, pr, psx, psy = self.pai.mundo()
        dx, dy = x - px, y - py
        c, s = math.cos(math.radians(-pr)), math.sin(math.radians(-pr))
        self.x = (dx * c - dy * s) / (psx or 1e-9)
        self.y = (dx * s + dy * c) / (psy or 1e-9)
        if rotacao is not None:
            self.rotacao = rotacao - pr
        if escala_x is not None:
            self.escala_x = escala_x / (psx or 1e-9)
            self.escala_y = (escala_y if escala_y is not None else escala_x) / (psy or 1e-9)

    # --- utilidades ------------------------------------------------------------
    def transladar(self, dx: float, dy: float) -> None:
        self.x += dx
        self.y += dy

    def olhar_para(self, x: float, y: float) -> None:
        """Gira para que o eixo +x local aponte para (x, y) no mundo."""
        wx, wy = self.posicao_mundo
        ang = math.degrees(math.atan2(y - wy, x - wx))
        pr = self.pai.mundo()[2] if self.pai else 0.0
        self.rotacao = ang - pr

    def distancia(self, outro: "Transform") -> float:
        ax, ay = self.posicao_mundo
        bx, by = outro.posicao_mundo
        return math.hypot(ax - bx, ay - by)


class GameObject:
    def __init__(self, nome: str = "GameObject", x=0.0, y=0.0, rotacao=0.0, escala=1.0,
                 tag: str = "", pai: "GameObject | None" = None):
        self.id = next(_ids)
        self.nome = nome
        self.tag = tag
        self._ativo = True
        self.transform = Transform(self, x, y, rotacao, escala, escala)
        self.componentes: list[Componente] = []
        self.cena = None
        self.destruido = False
        self.indice_hierarquia = 0     # posição na Hierarchy (desempate da ordem de desenho)
        self.oculto = False            # objeto auxiliar criado por um componente: não aparece nem é salvo
        if pai is not None:
            self.transform.definir_pai(pai.transform)

    # --- componentes ---------------------------------------------------------
    def adicionar(self, comp, **campos) -> "Componente":
        """Anexa um componente (instância ou classe + campos)."""
        if isinstance(comp, type):
            comp = comp(**campos)
        comp.gameobject = self
        self.componentes.append(comp)
        if self.cena is not None:
            self.cena._agendar_inicio(comp)
        return comp

    def obter(self, tipo) -> "Componente | None":
        """Primeiro componente do tipo (classe ou nome da classe)."""
        for c in self.componentes:
            if (isinstance(tipo, str) and type(c).__name__ == tipo) or \
                    (isinstance(tipo, type) and isinstance(c, tipo)):
                return c
        return None

    def obter_todos(self, tipo) -> list:
        return [c for c in self.componentes
                if (isinstance(tipo, str) and type(c).__name__ == tipo) or
                (isinstance(tipo, type) and isinstance(c, tipo))]

    def obter_nos_filhos(self, tipo) -> list:
        saida = list(self.obter_todos(tipo))
        for f in self.transform.filhos:
            saida += f.gameobject.obter_nos_filhos(tipo)
        return saida

    def remover_componente(self, comp: "Componente") -> None:
        if comp in self.componentes:
            comp.ao_destruir()
            self.componentes.remove(comp)

    # --- estado ----------------------------------------------------------------
    @property
    def ativo(self) -> bool:
        return self._ativo

    @ativo.setter
    def ativo(self, v: bool) -> None:
        self._ativo = bool(v)

    @property
    def ativo_na_hierarquia(self) -> bool:
        t = self.transform
        while t is not None:
            if not t.gameobject._ativo:
                return False
            t = t.pai
        return True

    @property
    def filhos(self) -> list["GameObject"]:
        return [t.gameobject for t in self.transform.filhos]

    @property
    def pai(self) -> "GameObject | None":
        return self.transform.pai.gameobject if self.transform.pai else None

    def destruir(self, atraso: float = 0.0) -> None:
        if self.cena is not None:
            self.cena.destruir(self, atraso)
        else:
            self.destruido = True

    def __repr__(self) -> str:
        return f"<GameObject {self.nome!r} #{self.id}>"


class Componente:
    CAMPOS: dict[str, str] = {}   # nome do atributo → tipo (float, int, bool, str, cor)
    MENU = "Scripts"              # categoria no "Adicionar Componente" do editor
    EXECUTA_NO_EDITOR = False     # True: iniciar() roda também no modo de edição (ex.: SpriteRenderer)

    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
        REGISTRO_COMPONENTES[cls.__name__] = cls

    def __init__(self, **campos):
        self.gameobject: GameObject | None = None
        self.habilitado = True
        self._iniciado = False
        for k, v in campos.items():
            if not hasattr(type(self), k) and k not in self._todos_campos():
                raise TypeError(f"{type(self).__name__} não tem o campo '{k}'")
            setattr(self, k, v)

    @classmethod
    def _todos_campos(cls) -> dict:
        campos = {}
        for base in reversed(cls.__mro__):
            campos.update(getattr(base, "CAMPOS", {}))
        return campos

    # atalhos
    @property
    def transform(self) -> Transform:
        return self.gameobject.transform

    @property
    def cena(self):
        return self.gameobject.cena

    @property
    def motor(self):
        return self.gameobject.cena.motor if self.gameobject.cena else None

    def obter(self, tipo):
        return self.gameobject.obter(tipo)

    # ganchos (sobrescreva nas subclasses)
    def iniciar(self) -> None: ...
    def atualizar(self, dt: float) -> None: ...
    def atualizar_tardio(self, dt: float) -> None: ...   # depois de todos os atualizar()
    def ao_entrar_colisao(self, outro) -> None: ...
    def ao_sair_colisao(self, outro) -> None: ...
    def desenhar_ui(self, ui) -> None: ...
    def ao_destruir(self) -> None: ...

    # serialização (cena/prefab em JSON e inspector)
    def para_dict(self) -> dict:
        return {"tipo": type(self).__name__,
                "campos": {k: _json(getattr(self, k)) for k in self._todos_campos()}}


def _json(v):
    if isinstance(v, tuple):
        return list(v)
    return v


class ComponenteAusente(Componente):
    """Guarda os dados de um componente cujo script não existe ou tem erro, para não perdê-los."""

    MENU = ""

    def __init__(self, tipo_original: str = "?", campos_originais: dict | None = None):
        super().__init__()
        self.tipo_original = tipo_original
        self.campos_originais = dict(campos_originais or {})

    def para_dict(self) -> dict:
        return {"tipo": self.tipo_original, "campos": self.campos_originais}

    def linhas_inspector(self) -> list[str]:
        return [f"Script '{self.tipo_original}' não encontrado ou com erro.",
                "Corrija o script: os valores salvos serão mantidos."]

