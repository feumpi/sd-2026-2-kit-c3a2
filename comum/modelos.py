"""
Entradas validadas, iguais no gateway e na inferencia.

Os dois lados usam os mesmos limites para que uma entrada invalida seja recusada ja no
gateway, sem gerar chamada remota nem contar como falha no disjuntor.
"""
import os
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, StringConstraints

TEXTO_MAXIMO = int(os.getenv("TEXTO_MAXIMO", "5000"))
TOP_K_PADRAO = int(os.getenv("TOP_K", "3"))
TOP_K_MAXIMO = 20


def _sem_nulo(valor: str) -> str:
    # o Postgres nao aceita o caractere nulo em colunas de texto
    if "\x00" in valor:
        raise ValueError("caractere nulo nao e permitido")
    return valor


def _texto(maximo: int):
    return Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=maximo),
        AfterValidator(_sem_nulo),
    ]


Texto = _texto(TEXTO_MAXIMO)
Origem = _texto(200)


class EntradaTexto(BaseModel):
    texto: Texto


class Documento(BaseModel):
    texto: Texto
    origem: Origem = "desconhecida"


class Consulta(BaseModel):
    pergunta: Texto
    top_k: int = Field(default=TOP_K_PADRAO, ge=1, le=TOP_K_MAXIMO)
