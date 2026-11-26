"""
Acesso ao armazenamento vetorial (Postgres + pgvector).

Usado pelo worker (unico escritor) e pela inferencia (somente leitura). Toda operacao tem
tempo-limite: para obter conexao, para conectar e para executar o comando.

O vetor viaja como texto convertido com `::vector`, sem registrar tipo na conexao: assim a
conexao funciona mesmo antes de a extensao existir (a inferencia pode subir antes do worker).
"""
import hashlib
import os
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DIMENSAO = 512
URL_PADRAO = "postgresql://postgres:postgres@vetorial:5432/plataforma"
ESQUEMA = Path(__file__).with_name("esquema.sql")


class BancoIndisponivel(Exception):
    """Falha transitoria: banco fora do ar, lento ou sem conexao livre."""


class EsquemaAusente(BancoIndisponivel):
    """A tabela ou a extensao ainda nao foram criadas pelo worker."""


def id_documento(texto: str, origem: str) -> str:
    """O mesmo documento sempre tem o mesmo id: regravar nao duplica."""
    return hashlib.sha256(f"{origem}\n{texto}".encode("utf-8")).hexdigest()


class Repositorio:

    def __init__(self, url: str | None = None):
        tempo = float(os.getenv("DB_TIMEOUT", "5"))
        self._pool = ConnectionPool(
            url or os.getenv("DATABASE_URL", URL_PADRAO),
            min_size=0,
            max_size=int(os.getenv("DB_POOL_MAXIMO", "3")),
            timeout=tempo,
            reconnect_timeout=tempo,
            kwargs={"connect_timeout": max(2, int(tempo)),
                    "options": f"-c statement_timeout={int(tempo * 1000)}"},
            check=ConnectionPool.check_connection,
            open=False,
        )

    @contextmanager
    def _conexao(self):
        """Conexao do pool; confirma ao sair e traduz as falhas transitorias."""
        try:
            self._pool.open()
            with self._pool.connection() as conexao:
                yield conexao
        except (psycopg.errors.UndefinedTable, psycopg.errors.UndefinedObject) as erro:
            raise EsquemaAusente(type(erro).__name__) from erro
        except psycopg.OperationalError as erro:
            raise BancoIndisponivel(type(erro).__name__) from erro

    def aplicar_esquema(self) -> None:
        with self._conexao() as conexao:
            conexao.execute(ESQUEMA.read_text(encoding="utf-8").encode("utf-8"))

    def gravar(self, texto: str, origem: str, sentimento: str, confianca: float,
               vetor: list[float]) -> tuple[str, bool]:
        """Grava o documento; devolve (id, novo). Regravar o mesmo documento nao faz nada."""
        documento_id = id_documento(texto, origem)
        with self._conexao() as conexao:
            cursor = conexao.execute(
                "INSERT INTO documentos (id, origem, texto, sentimento, confianca, vetor) "
                "VALUES (%s, %s, %s, %s, %s, %s::vector) ON CONFLICT (id) DO NOTHING",
                (documento_id, origem, texto, sentimento, confianca, str(vetor)),
            )
            return documento_id, cursor.rowcount == 1

    def buscar(self, vetor: list[float], top_k: int) -> list[dict]:
        """Os top_k documentos mais parecidos (similaridade do cosseno)."""
        with self._conexao() as conexao:
            cursor = conexao.cursor(row_factory=dict_row)
            cursor.execute(
                "SELECT origem, texto, sentimento, 1 - (vetor <=> %(vetor)s::vector) AS score "
                "FROM documentos ORDER BY vetor <=> %(vetor)s::vector LIMIT %(limite)s",
                {"vetor": str(vetor), "limite": top_k},
            )
            return cursor.fetchall()

    def expurgar(self, dias: float) -> int:
        """Retencao (LGPD): apaga documentos mais antigos que o prazo."""
        with self._conexao() as conexao:
            return conexao.execute(
                "DELETE FROM documentos WHERE criado_em < now() - %s * interval '1 day'",
                (dias,),
            ).rowcount

    def fechar(self) -> None:
        self._pool.close()
