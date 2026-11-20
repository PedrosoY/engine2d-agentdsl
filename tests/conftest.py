import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))


class TexturaFalsa:
    """Substitui a textura OpenGL nos testes que não precisam de GPU."""

    def __init__(self, largura=64, altura=32, id_=1, nome="falsa"):
        self.largura, self.altura, self.id, self.nome = largura, altura, id_, nome


class MotorFalso:
    largura, altura = 800, 600
