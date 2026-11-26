"""Testes do acesso ao armazenamento vetorial, com o pool substituido (sem banco)."""
from contextlib import contextmanager

import psycopg
import pytest
from psycopg_pool import PoolTimeout

from vetorial import repositorio
from vetorial.repositorio import BancoIndisponivel, EsquemaAusente, Repositorio, id_documento


class Cursor:
    def __init__(self, rowcount=1):
        self.rowcount = rowcount


class Conexao:
    def __init__(self, resultado):
        self.resultado = resultado
        self.comandos = []

    def execute(self, sql, parametros=None):
        self.comandos.append((sql, parametros))
        if isinstance(self.resultado, Exception):
            raise self.resultado
        return self.resultado


class Pool:
    def __init__(self, conexao=None, erro=None):
        self.conexao, self.erro = conexao, erro

    def open(self):
        pass

    @contextmanager
    def connection(self):
        if self.erro:
            raise self.erro
        yield self.conexao


def com_pool(pool):
    repo = Repositorio("postgresql://x:y@127.0.0.1:1/z")
    repo._pool = pool
    return repo


def test_id_depende_da_origem_e_do_texto():
    assert id_documento("a", "o") == id_documento("a", "o")
    assert id_documento("a", "o") != id_documento("a", "outra")
    assert len(id_documento("a", "o")) == 64


def test_gravacao_e_idempotente_pelo_comando():
    conexao = Conexao(Cursor(rowcount=0))
    documento_id, novo = com_pool(Pool(conexao)).gravar("t", "o", "positivo", 0.9, [0.5, 0.5])
    sql, parametros = conexao.comandos[0]
    assert "ON CONFLICT (id) DO NOTHING" in sql
    assert parametros[0] == documento_id and parametros[-1] == "[0.5, 0.5]"
    assert novo is False


def test_expurgo_usa_o_prazo_em_dias():
    conexao = Conexao(Cursor(rowcount=4))
    assert com_pool(Pool(conexao)).expurgar(30) == 4
    sql, parametros = conexao.comandos[0]
    assert "DELETE FROM documentos" in sql and "criado_em" in sql
    assert parametros == (30,)


@pytest.mark.parametrize("erro", [PoolTimeout("cheio"), psycopg.OperationalError("caiu"),
                                  psycopg.errors.QueryCanceled("lento")])
def test_falha_de_conexao_ou_tempo_vira_banco_indisponivel(erro):
    with pytest.raises(BancoIndisponivel):
        com_pool(Pool(erro=erro)).expurgar(1)


@pytest.mark.parametrize("erro", [psycopg.errors.UndefinedTable("sem tabela"),
                                  psycopg.errors.UndefinedObject("sem tipo vector")])
def test_esquema_ausente_e_identificado(erro):
    with pytest.raises(EsquemaAusente):
        com_pool(Pool(Conexao(erro))).expurgar(1)


def test_erro_nos_dados_nao_e_tratado_como_transitorio():
    with pytest.raises(psycopg.DataError):
        com_pool(Pool(Conexao(psycopg.DataError("ruim")))).expurgar(1)


def test_dimensao_do_esquema_bate_com_o_codigo():
    assert f"vector({repositorio.DIMENSAO})" in repositorio.ESQUEMA.read_text(encoding="utf-8")
