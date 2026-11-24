"""O que vários scripts da navinha usam: a área de jogo, os sons, explosões e o placar."""
import json
import random
from pathlib import Path

# Área onde a batalha acontece (o resto da tela são os painéis do placar).
ESQUERDA, DIREITA, BAIXO, CIMA = 180.0, 720.0, 0.0, 600.0
CENTRO_X = (ESQUERDA + DIREITA) / 2

SONS = {
    "laser": "Assets/Sons/sfx_laser1.ogg",
    "laser_inimigo": "Assets/Sons/sfx_laser2.ogg",
    "explosao": "Assets/Sons/explosao.wav",
    "acerto": "Assets/Sons/sfx_zap.ogg",
    "item": "Assets/Sons/sfx_shieldUp.ogg",
    "escudo_caiu": "Assets/Sons/sfx_shieldDown.ogg",
    "perdeu": "Assets/Sons/sfx_lose.ogg",
    "alerta": "Assets/Sons/sfx_twoTone.ogg",
}
FONTE = "Assets/Fontes/kenvector_future.ttf"
RECORDE = Path("Saves/recorde.json")


def tocar(cena, som, volume=0.7):
    if cena is not None and cena.motor is not None:
        cena.motor.audio.tocar(SONS.get(som, som), volume, variar=0.2)


def explosao(cena, x, y, tamanho=1.0, som=True):
    """Cria o prefab da explosão (partículas) e toca o som."""
    go = cena.instanciar("Assets/Prefabs/explosao.prefab", x, y)
    go.transform.escala_x = go.transform.escala_y = tamanho
    em = go.obter("EmissorParticulas")
    if em is not None:
        em.rajada = int(em.rajada * tamanho)
        em.velocidade *= 0.6 + 0.4 * tamanho
        em.tamanho_inicial *= 0.7 + 0.3 * tamanho
    luz = go.obter("Luz2D")                  # o clarão ilumina mais longe nas explosões grandes
    if luz is not None:
        luz.raio *= 0.6 + 0.4 * tamanho
        luz.apagar_em *= 0.8 + 0.2 * tamanho
    if som:
        tocar(cena, "explosao", min(1.0, 0.35 + 0.25 * tamanho))
    if tamanho >= 1.2 and cena.motor is not None:      # explosão grande: a tela treme
        cena.motor.tremer(3.0 * tamanho, 0.25 + 0.1 * tamanho)
    return go


def faisca(cena, x, y):
    cena.instanciar("Assets/Prefabs/faisca.prefab", x, y)


def hud(cena):
    go = cena.encontrar("HUD") if cena is not None else None
    return go.obter("Hud") if go is not None else None


def jogador(cena):
    go = cena.encontrar("Jogador") if cena is not None else None
    if go is None or go.destruido:
        return None
    return go.obter("Jogador")


def dentro(x, y, margem=0.0):
    return ESQUERDA - margem <= x <= DIREITA + margem and BAIXO - margem <= y <= CIMA + margem


def x_aleatorio(margem=40.0):
    return random.uniform(ESQUERDA + margem, DIREITA - margem)


def ler_recorde() -> int:
    try:
        return int(json.loads(RECORDE.read_text(encoding="utf-8")).get("recorde", 0))
    except (OSError, ValueError):
        return 0


def salvar_recorde(pontos: int) -> bool:
    """Guarda o recorde se ``pontos`` for maior. Devolve True se bateu o recorde."""
    if pontos <= ler_recorde():
        return False
    RECORDE.parent.mkdir(parents=True, exist_ok=True)
    RECORDE.write_text(json.dumps({"recorde": int(pontos)}), encoding="utf-8")
    return True
