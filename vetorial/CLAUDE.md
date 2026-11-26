# vetorial/ — armazenamento vetorial (Postgres + pgvector)

Quarto serviço da arquitetura (R2). Local: container próprio. Nuvem: Neon. O mesmo SQL e o
mesmo código servem aos dois, trocando só `DATABASE_URL`.

Substitui o índice JSON do C2 (`referencia/c2a2/ingestao_indice.py`), de onde vêm o id por
hash e a idempotência.

## A criar

- `Dockerfile`: `FROM pgvector/pgvector:pg17`, copiando `esquema.sql` para
  `/docker-entrypoint-initdb.d/`.
- `esquema.sql` (idempotente):

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS documentos (
    id         text PRIMARY KEY,
    origem     text NOT NULL,
    texto      text NOT NULL,
    sentimento text NOT NULL,
    confianca  real NOT NULL,
    vetor      vector(512) NOT NULL,
    criado_em  timestamptz NOT NULL DEFAULT now()
);
```

- Módulo Python de acesso a dados (ex.: `repositorio.py` + `__init__.py`), usado por worker
  (gravar, expurgar, aplicar o esquema na subida) e inferência (buscar). Ambas as imagens
  precisam copiar `vetorial/`.

Busca: `1 - (vetor <=> %s)` como `score`, `ORDER BY vetor <=> %s LIMIT %s`. O corpus é
pequeno: não precisa de índice HNSW.

## Cuidados

- A dimensão (512) precisa bater com `inferencia/embeddings.py`.
- `register_vector(conn)` (pacote `pgvector.psycopg`) só funciona depois de criada a extensão.
- Neon suspende o banco ocioso e derruba conexões: use `ConnectionPool` com
  `check=ConnectionPool.check_connection` e `connect_timeout`.
- Na connection string com pooler do Neon (PgBouncer em modo transação), use
  `prepare_threshold=None`. `sslmode=require` vem na própria string.
- Healthcheck no compose: `pg_isready -h 127.0.0.1` (pelo socket ele responde "pronto" ainda
  durante a inicialização).
- Imagem `pg17` e projeto Neon em Postgres 17 (o padrão do Neon é 18: escolha 17 ao criar).
- Defina `statement_timeout` ou equivalente: toda chamada tem tempo-limite.
