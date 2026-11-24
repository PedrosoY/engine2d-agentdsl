"""O que vários scripts do jogo de plataforma usam: sons, recorde e atalhos para achar objetos."""
import json
from pathlib import Path

SONS = {
    "pulo": "Assets/Sons/sfx_jump.ogg",
    "pulo_alto": "Assets/Sons/sfx_jump-high.ogg",
    "moeda": "Assets/Sons/sfx_coin.ogg",
    "batida": "Assets/Sons/sfx_bump.ogg",
    "dano": "Assets/Sons/sfx_hurt.ogg",
    "poder": "Assets/Sons/sfx_magic.ogg",
    "pisao": "Assets/Sons/sfx_disappear.ogg",
    "aparece": "Assets/Sons/sfx_throw.ogg",
    "alerta": "Assets/Sons/sfx_select.ogg",
    "vitoria": "Assets/Sons/sfx_gem.ogg",
}
RECORDE = Path("Saves/recorde.json")


def tocar(cena, som, volume=0.6):
    if cena is not None and cena.motor is not None:
        cena.motor.audio.tocar(SONS.get(som, som), volume, variar=0.1)


def achar(cena, nome, componente):
    go = cena.encontrar(nome) if cena is not None else None
    return go.obter(componente) if go is not None and not go.destruido else None


def hud(cena):
    return achar(cena, "HUD", "Hud")


def jogador(cena):
    return achar(cena, "Jogador", "Jogador")


def poeira(cena, x, y, n=8):
    """Nuvenzinha de poeira (pulo, pouso, pisão)."""
    go = cena.instanciar("Assets/Prefabs/poeira.prefab", x, y)
    em = go.obter("EmissorParticulas")
    if em is not None:
        em.rajada = n


def ler_recorde() -> int:
    try:
        return int(json.loads(RECORDE.read_text(encoding="utf-8")).get("recorde", 0))
    except (OSError, ValueError):
        return 0


def salvar_recorde(pontos: int) -> bool:
    if pontos <= ler_recorde():
        return False
    RECORDE.parent.mkdir(parents=True, exist_ok=True)
    RECORDE.write_text(json.dumps({"recorde": int(pontos)}), encoding="utf-8")
    return True
