"""
Rate limit por cliente e por minuto (Aula 8): janela fixa no Redis.

Cliente = `sub` do token; no /login, ainda sem token, o IP. Nos dois casos a chave guarda
so um HMAC com o segredo do gateway (um hash simples de IPv4 seria revertido por forca
bruta) e expira em 60 s. Redis fora do ar: a requisicao passa e o aviso vai para o log
(prioriza disponibilidade).
"""
import hashlib
import hmac
import logging
import os
import time

import redis
from fastapi import Depends, HTTPException, Request

from gateway.autenticacao import exigir_usuario, segredo

log = logging.getLogger("gateway")

JANELA = 60
LIMITE = int(os.getenv("LIMITE_POR_MINUTO", "60"))
# de onde vem o IP real atras de um proxy; vazio/0 = endereco da conexao
CABECALHO_IP = os.getenv("CABECALHO_IP_CLIENTE", "")
PROXIES_CONFIAVEIS = int(os.getenv("PROXIES_CONFIAVEIS", "0"))


def endereco_do_cliente(request: Request) -> str:
    """IP do cliente, sem confiar no que ele mesmo pode escrever no X-Forwarded-For."""
    if CABECALHO_IP and (valor := request.headers.get(CABECALHO_IP, "").strip()):
        return valor
    if PROXIES_CONFIAVEIS > 0:
        # cada proxy ACRESCENTA ao fim: o que vem antes pode ter sido forjado
        cadeia = [p.strip() for p in request.headers.get("X-Forwarded-For", "").split(",")
                  if p.strip()]
        if len(cadeia) >= PROXIES_CONFIAVEIS:
            return cadeia[-PROXIES_CONFIAVEIS]
    return request.client.host if request.client else "desconhecido"


def chave(cliente: str, janela: int) -> str:
    resumo = hmac.new(segredo().encode(), cliente.encode(), hashlib.sha256).hexdigest()
    return f"limite:{resumo}:{janela}"


def consumir(r, cliente: str) -> None:
    """Conta uma requisicao; levanta 429 com Retry-After se o limite da janela estourou."""
    agora = time.time()
    nome = chave(cliente, int(agora // JANELA))
    try:
        # transacao: a chave nunca fica sem prazo
        with r.pipeline(transaction=True) as lote:
            lote.set(nome, 0, ex=JANELA, nx=True)
            lote.incr(nome)
            total = lote.execute()[-1]
    except redis.RedisError as erro:
        log.warning("rate limit indisponivel, requisicao liberada: %s", type(erro).__name__)
        return
    if total > LIMITE:
        restante = max(1, JANELA - int(agora % JANELA))
        raise HTTPException(429, "limite de requisicoes por minuto excedido",
                            headers={"Retry-After": str(restante)})


def _cliente_redis(request: Request):
    return request.app.state.redis()


def limitar_usuario(usuario: str = Depends(exigir_usuario),
                    r=Depends(_cliente_redis)) -> None:
    consumir(r, f"usuario:{usuario}")


def limitar_endereco(request: Request, r=Depends(_cliente_redis)) -> None:
    consumir(r, f"ip:{endereco_do_cliente(request)}")
