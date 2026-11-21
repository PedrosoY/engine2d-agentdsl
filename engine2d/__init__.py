"""Engine2D: mini engine 2D em Python + OpenGL com arquitetura no estilo Unity/Godot.

    from engine2d import Motor, Cena, Componente, SpriteRenderer, Colisor, CorpoRigido

    class Girar(Componente):
        CAMPOS = {"velocidade": "float"}
        velocidade = 90.0
        def atualizar(self, dt):
            self.transform.rotacao += self.velocidade * dt

    motor = Motor(pasta_assets="assets")
    cena = Cena()
    cena.criar("Estrela", 640, 360, componentes=[SpriteRenderer(imagem="estrela.png"), Girar()])
    motor.executar(cena)
"""
import os

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import OpenGL

# O PyOpenGL chama glGetError depois de CADA função por padrão, o que custa
# dezenas de microssegundos por chamada. Defina ENGINE2D_DEBUG_GL=1 para religar.
if os.environ.get("ENGINE2D_DEBUG_GL") != "1":
    OpenGL.ERROR_CHECKING = False
    OpenGL.ERROR_LOGGING = False

from .camera import Camera2D  # noqa: E402
from .cena import Cena  # noqa: E402
from .componentes import (Animador, CameraSegue, Colisor, CorpoRigido, Piscar,  # noqa: E402
                          SpriteRenderer, TempoDeVida)
from .lista_render import ListaRenderizacao  # noqa: E402
from .objeto import Componente, GameObject, Transform  # noqa: E402
from .sprite import Sprite  # noqa: E402
from .transformacao import Transformacao  # noqa: E402

__all__ = ["Camera2D", "Cena", "Componente", "GameObject", "Transform", "SpriteRenderer", "Colisor",
           "CorpoRigido", "Animador", "CameraSegue", "Piscar", "TempoDeVida", "ListaRenderizacao",
           "Sprite", "Transformacao", "Motor", "Textura"]


def __getattr__(nome):
    # Importação preguiçosa: módulos que abrem janela/OpenGL só carregam quando usados
    # (assim os testes de cena/física rodam sem GPU).
    if nome == "Motor":
        from .motor import Motor
        return Motor
    if nome == "Textura":
        from .textura import Textura
        return Textura
    raise AttributeError(nome)
