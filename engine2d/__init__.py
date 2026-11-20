"""Mini engine gráfica 2D para renderização e manipulação de sprites com OpenGL."""
import os

import OpenGL

# O PyOpenGL chama glGetError depois de CADA função por padrão, o que custa
# dezenas de microssegundos por chamada. Defina ENGINE2D_DEBUG_GL=1 para religar.
if os.environ.get("ENGINE2D_DEBUG_GL") != "1":
    OpenGL.ERROR_CHECKING = False
    OpenGL.ERROR_LOGGING = False
from .camera import Camera2D
from .cena import Cena
from .sprite import Sprite
from .transformacao import Transformacao

__all__ = ["Camera2D", "Cena", "Sprite", "Transformacao", "Motor", "TextoHUD", "Textura"]


def __getattr__(nome):
    # Importação preguiçosa: os módulos que dependem de OpenGL/pygame só são
    # carregados quando usados (assim os testes de matemática/cena rodam sem GPU).
    if nome in ("Motor", "TextoHUD"):
        from . import motor
        return getattr(motor, nome)
    if nome == "Textura":
        from .textura import Textura
        return Textura
    raise AttributeError(nome)
