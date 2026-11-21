import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.environ["ENGINE2D_LEVANTAR_ERROS"] = "1"   # nos testes, erro tem que falhar o teste


class TexturaFalsa:
    """Substitui a textura OpenGL nos testes que não precisam de GPU."""

    def __init__(self, largura=64, altura=32, id_=1, nome="falsa"):
        self.largura, self.altura, self.id, self.nome = largura, altura, id_, nome


class MotorFalso:
    largura, altura = 800, 600
