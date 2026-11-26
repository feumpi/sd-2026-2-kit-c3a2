"""
Autenticacao por JWT (Aula 16): POST /login emite o token e as rotas de negocio o exigem.

Falha fechada: sem segredo de 32 bytes o gateway nao sobe; sem usuario e senha
configurados todo login e recusado. Nada daqui vai para o log.
"""
import hmac
import os
import time

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

ALGORITMO = "HS256"
TAMANHO_MINIMO_SEGREDO = 32
EXPIRA_MIN = int(os.getenv("JWT_EXPIRA_MIN", "60"))

roteador = APIRouter(tags=["autenticacao"])
# auto_error=False: o 401 e montado aqui, sempre com o mesmo corpo
esquema_bearer = HTTPBearer(auto_error=False, description="Token devolvido por POST /login")


class Credenciais(BaseModel):
    usuario: str = Field(min_length=1, max_length=100)
    senha: str = Field(min_length=1, max_length=200)


def segredo() -> str:
    valor = os.getenv("JWT_SEGREDO", "")
    if len(valor.encode()) < TAMANHO_MINIMO_SEGREDO:
        raise RuntimeError(f"JWT_SEGREDO precisa de pelo menos {TAMANHO_MINIMO_SEGREDO} bytes")
    return valor


def _igual(recebido: str, esperado: str) -> bool:
    # comparacao em tempo constante; valor esperado vazio nunca confere
    return bool(esperado) and hmac.compare_digest(recebido.encode(), esperado.encode())


def credenciais_validas(usuario: str, senha: str) -> bool:
    usuario_ok = _igual(usuario, os.getenv("USUARIO_DEMO", ""))
    senha_ok = _igual(senha, os.getenv("SENHA_DEMO", ""))
    return usuario_ok and senha_ok


def emitir_token(usuario: str, minutos: float = EXPIRA_MIN) -> str:
    agora = int(time.time())
    return jwt.encode({"sub": usuario, "iat": agora, "exp": agora + int(minutos * 60)},
                      segredo(), algorithm=ALGORITMO)


def _nao_autorizado(mensagem: str) -> HTTPException:
    return HTTPException(401, mensagem, headers={"WWW-Authenticate": "Bearer"})


def exigir_usuario(
    credenciais: HTTPAuthorizationCredentials | None = Depends(esquema_bearer),
) -> str:
    """Dependencia das rotas protegidas: devolve o `sub` do token ou 401."""
    if credenciais is None:
        raise _nao_autorizado("token ausente, invalido ou expirado")
    try:
        dados = jwt.decode(credenciais.credentials, segredo(), algorithms=[ALGORITMO],
                           options={"require": ["exp", "sub"]})
    except jwt.InvalidTokenError as erro:
        raise _nao_autorizado("token ausente, invalido ou expirado") from erro
    return dados["sub"]


@roteador.post("/login")
def login(entrada: Credenciais):
    """Troca usuario e senha por um token JWT com prazo de validade."""
    if not credenciais_validas(entrada.usuario, entrada.senha):
        raise _nao_autorizado("usuario ou senha invalidos")
    return {"token": emitir_token(entrada.usuario), "tipo": "bearer",
            "expira_em_segundos": EXPIRA_MIN * 60}
