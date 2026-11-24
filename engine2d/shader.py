"""Compilação e uso de programas GLSL."""
from __future__ import annotations

import numpy as np
from OpenGL import GL


class ErroShader(RuntimeError):
    pass


class Shader:
    def __init__(self, fonte_vertex: str, fonte_fragment: str):
        vs = self._compilar(fonte_vertex, GL.GL_VERTEX_SHADER)
        fs = self._compilar(fonte_fragment, GL.GL_FRAGMENT_SHADER)
        self.programa = GL.glCreateProgram()
        GL.glAttachShader(self.programa, vs)
        GL.glAttachShader(self.programa, fs)
        GL.glLinkProgram(self.programa)
        if not GL.glGetProgramiv(self.programa, GL.GL_LINK_STATUS):
            raise ErroShader(GL.glGetProgramInfoLog(self.programa).decode())
        GL.glDeleteShader(vs)
        GL.glDeleteShader(fs)
        self._locais: dict[str, int] = {}

    @staticmethod
    def _compilar(fonte: str, tipo) -> int:
        sh = GL.glCreateShader(tipo)
        GL.glShaderSource(sh, fonte)
        GL.glCompileShader(sh)
        if not GL.glGetShaderiv(sh, GL.GL_COMPILE_STATUS):
            raise ErroShader(GL.glGetShaderInfoLog(sh).decode())
        return sh

    def usar(self) -> None:
        GL.glUseProgram(self.programa)

    def _local(self, nome: str) -> int:
        if nome not in self._locais:
            self._locais[nome] = GL.glGetUniformLocation(self.programa, nome)
        return self._locais[nome]

    def mat3(self, nome: str, m: np.ndarray) -> None:
        # numpy é linha-maior; GL_TRUE transpõe para a convenção coluna-maior do GLSL.
        GL.glUniformMatrix3fv(self._local(nome), 1, GL.GL_TRUE, np.ascontiguousarray(m, dtype=np.float32))

    def vec4(self, nome: str, v) -> None:
        GL.glUniform4f(self._local(nome), *v)

    def int(self, nome: str, v: int) -> None:
        GL.glUniform1i(self._local(nome), v)

    def float(self, nome: str, v: float) -> None:
        GL.glUniform1f(self._local(nome), v)

    def vec2(self, nome: str, v) -> None:
        GL.glUniform2f(self._local(nome), *v)


# ---------------------------------------------------------------------------
# Shaders da engine
# ---------------------------------------------------------------------------
# Modo "individual": uma chamada de desenho por sprite, matriz via uniform.
VERTEX_INDIVIDUAL = """
#version 330 core
layout(location = 0) in vec2 a_pos;   // quad unitário [-0.5, 0.5]
layout(location = 1) in vec2 a_uv;
uniform mat3 u_viewproj;
uniform mat3 u_modelo;
uniform vec4 u_cor;
uniform vec4 u_regiao_uv;            // (u0, v0, u1, v1)
uniform float u_iluminado;           // 1 = recebe a luz do mapa de luz, 0 = brilho próprio
out vec2 v_uv;
out vec4 v_cor;
out float v_ilum;
void main() {
    vec3 p = u_viewproj * u_modelo * vec3(a_pos, 1.0);   // v' = M v (eq. 7)
    gl_Position = vec4(p.xy, 0.0, 1.0);
    v_uv = mix(u_regiao_uv.xy, u_regiao_uv.zw, a_uv);
    v_cor = u_cor;
    v_ilum = u_iluminado;
}
"""

# Modo "lote": instancing. A matriz de modelo vem como 3 atributos por instância.
VERTEX_LOTE = """
#version 330 core
layout(location = 0) in vec2 a_pos;
layout(location = 1) in vec2 a_uv;
layout(location = 2) in vec3 i_col0;   // colunas da matriz de modelo
layout(location = 3) in vec3 i_col1;
layout(location = 4) in vec3 i_col2;
layout(location = 5) in vec4 i_cor;
layout(location = 6) in vec4 i_regiao_uv;
layout(location = 7) in float i_iluminado;
uniform mat3 u_viewproj;
out vec2 v_uv;
out vec4 v_cor;
out float v_ilum;
void main() {
    mat3 modelo = mat3(i_col0, i_col1, i_col2);
    vec3 p = u_viewproj * modelo * vec3(a_pos, 1.0);
    gl_Position = vec4(p.xy, 0.0, 1.0);
    v_uv = mix(i_regiao_uv.xy, i_regiao_uv.zw, a_uv);
    v_cor = i_cor;
    v_ilum = i_iluminado;
}
"""

# A cor do texel é multiplicada pela luz que chegou naquele pixel (mapa de luz desenhado antes,
# numa textura do tamanho da tela). gl_FragCoord diz qual pixel da tela está sendo pintado.
FRAGMENT = """
#version 330 core
in vec2 v_uv;
in vec4 v_cor;
in float v_ilum;
uniform sampler2D u_textura;
uniform sampler2D u_luz;      // mapa de luz (unidade 1)
uniform int u_com_luz;        // 0 = cena sem luzes (tudo com a cor normal)
uniform vec4 u_vp;            // viewport (x, y, largura, altura) para achar o pixel no mapa de luz
out vec4 cor_final;
void main() {
    vec4 texel = texture(u_textura, v_uv);
    cor_final = texel * v_cor;
    if (cor_final.a < 0.004) discard;   // pixels totalmente transparentes
    if (u_com_luz == 1) {
        vec3 luz = texture(u_luz, (gl_FragCoord.xy - u_vp.xy) / u_vp.zw).rgb;
        cor_final.rgb *= mix(vec3(1.0), luz, v_ilum);
    }
}
"""

# --- Iluminação 2D ------------------------------------------------------------------------------
# Cada luz é um quad (2 x raio) desenhado no mapa de luz com mistura aditiva (as luzes se somam).
VERTEX_LUZ = """
#version 330 core
layout(location = 0) in vec2 a_pos;
layout(location = 1) in vec2 a_uv;
uniform mat3 u_viewproj;
uniform mat3 u_modelo;
out vec2 v_local;             // -1..1 dentro do círculo da luz
void main() {
    vec3 p = u_viewproj * u_modelo * vec3(a_pos, 1.0);
    gl_Position = vec4(p.xy, 0.0, 1.0);
    v_local = a_pos * 2.0;
}
"""

FRAGMENT_LUZ = """
#version 330 core
in vec2 v_local;
uniform vec3 u_cor;           // cor x intensidade
uniform float u_interno;      // até aqui a luz é cheia (fração do raio)
uniform int u_cone;           // 1 = luz em cone (lanterna/farol)
uniform vec2 u_direcao;       // direção do cone
uniform vec2 u_abertura;      // (cos da metade da abertura, suavidade da borda)
out vec4 cor_final;
void main() {
    float d = length(v_local);
    if (d > 1.0) discard;
    float atenuacao = 1.0 - smoothstep(u_interno, 1.0, d);
    atenuacao *= atenuacao;                       // queda suave (parecida com 1/d²)
    if (u_cone == 1 && d > 0.001) {
        float c = dot(v_local / d, u_direcao);
        atenuacao *= smoothstep(u_abertura.x, u_abertura.x + u_abertura.y, c);
    }
    cor_final = vec4(u_cor * atenuacao, 1.0);
}
"""

# Sombras: triângulos em coordenadas do mundo, só para marcar o stencil (não pintam cor).
VERTEX_SOLIDO = """
#version 330 core
layout(location = 0) in vec2 a_pos;
uniform mat3 u_viewproj;
void main() {
    vec3 p = u_viewproj * vec3(a_pos, 1.0);
    gl_Position = vec4(p.xy, 0.0, 1.0);
}
"""

FRAGMENT_SOLIDO = """
#version 330 core
out vec4 cor_final;
void main() { cor_final = vec4(0.0); }
"""
