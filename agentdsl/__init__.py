"""AgentDSL: linguagem orientada a eventos para controlar agentes (sprites) da engine 2D.

Pipeline: Fonte → Lexer → Parser → AST → Análise semântica → Interpretador → Engine 2D
"""
from .erros import Diagnostico, ErroCompilacao, ErroExecucao
from .interpretador import AmbienteRegistro, SistemaAgentes, Simbolo, compilar
from .lexer import tokenizar
from .parser import analisar
from .semantica import ACOES_ENGINE, AnalisadorSemantico, Assinatura

__all__ = ["Diagnostico", "ErroCompilacao", "ErroExecucao", "AmbienteRegistro", "SistemaAgentes",
           "Simbolo", "compilar", "tokenizar", "analisar", "ACOES_ENGINE", "AnalisadorSemantico",
           "Assinatura"]
