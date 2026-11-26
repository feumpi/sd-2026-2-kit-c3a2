"""
Retentativa com espera progressiva (backoff exponencial + jitter) - Aula 11.

So retenta falhas TRANSITORIAS (tempo-limite, conexao recusada, HTTP 5xx e 429).
Erros do cliente (4xx) nao melhoram tentando de novo, entao sobem na hora.
Use apenas em operacoes idempotentes (inferencia, busca e geracao nao tem efeito colateral).
O log registra so o tipo do erro: a mensagem pode conter dados da requisicao (LGPD).
"""
import logging
import random
import time

import requests

log = logging.getLogger(__name__)


def eh_transitoria(erro: Exception) -> bool:
    if isinstance(erro, (requests.Timeout, requests.ConnectionError)):
        return True
    if isinstance(erro, requests.HTTPError) and erro.response is not None:
        codigo = erro.response.status_code
        return codigo >= 500 or codigo == 429
    return False


def espera_backoff(tentativa: int, base: float) -> float:
    """Espera antes da proxima tentativa: base, 2*base, 4*base... mais um jitter de ate base."""
    return base * 2 ** (tentativa - 1) + random.uniform(0, base)


def com_retentativa(funcao, tentativas=3, base=0.5, prazo_total=None, tempo_limite=None):
    """Devolve uma versao de `funcao` que retenta falhas transitorias com backoff.

    `prazo_total` (segundos) limita a sequencia inteira: nao comeca nova tentativa se a
    espera ja ultrapassar o prazo. Com `tempo_limite`, a funcao recebe o argumento
    `tempo_limite` de cada tentativa, encurtado para nao passar do que resta do prazo.
    """
    def envolvida(*args, **kwargs):
        inicio = time.monotonic()
        for tentativa in range(1, tentativas + 1):
            if tempo_limite is not None:
                limite = tempo_limite
                if prazo_total is not None:
                    restante = prazo_total - (time.monotonic() - inicio)
                    limite = max(0.1, min(tempo_limite, restante))
                kwargs["tempo_limite"] = limite
            try:
                return funcao(*args, **kwargs)
            except Exception as erro:
                if tentativa == tentativas or not eh_transitoria(erro):
                    raise
                espera = espera_backoff(tentativa, base)
                if prazo_total is not None and time.monotonic() - inicio + espera >= prazo_total:
                    raise
                log.warning("tentativa %d/%d falhou (%s); nova tentativa em %.2fs",
                            tentativa, tentativas, type(erro).__name__, espera)
                time.sleep(espera)
        raise ValueError("tentativas precisa ser ao menos 1")
    return envolvida
