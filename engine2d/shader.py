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
out vec2 v_uv;
out vec4 v_cor;
void main() {
    vec3 p = u_viewproj * u_modelo * vec3(a_pos, 1.0);   // v' = M v (eq. 7)
    gl_Position = vec4(p.xy, 0.0, 1.0);
    v_uv = mix(u_regiao_uv.xy, u_regiao_uv.zw, a_uv);
    v_cor = u_cor;
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
uniform mat3 u_viewproj;
out vec2 v_uv;
out vec4 v_cor;
void main() {
    mat3 modelo = mat3(i_col0, i_col1, i_col2);
    vec3 p = u_viewproj * modelo * vec3(a_pos, 1.0);
    gl_Position = vec4(p.xy, 0.0, 1.0);
    v_uv = mix(i_regiao_uv.xy, i_regiao_uv.zw, a_uv);
    v_cor = i_cor;
}
"""

FRAGMENT = """
#version 330 core
in vec2 v_uv;
in vec4 v_cor;
uniform sampler2D u_textura;
out vec4 cor_final;
void main() {
    vec4 texel = texture(u_textura, v_uv);
    cor_final = texel * v_cor;
    if (cor_final.a < 0.004) discard;   // pixels totalmente transparentes
}
"""
