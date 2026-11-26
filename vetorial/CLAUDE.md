# vetorial/ — armazenamento vetorial (Postgres + pgvector)

Quarto serviço da arquitetura (R2). Local: container próprio. Nuvem: Postgres gratuito do
Render. O mesmo SQL e o mesmo código servem aos dois, trocando só `DATABASE_URL`.

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
- O Render pode fazer manutenção no banco a qualquer momento: use `ConnectionPool` com
  `check=ConnectionPool.check_connection` e `connect_timeout`. Pool pequeno em cada serviço.
- Na nuvem o banco só é acessível pela rede privada (`ipAllowList: []`): o esquema é aplicado
  pelo worker na subida, não à mão.
- `CREATE EXTENSION vector` é suportado pelo Render.
- Não publique `5432:5432` (porta ocupada por outro banco no host). Se precisar depurar, use
  `5433:5432`. O padrão de `DATABASE_URL` no código nunca aponta para `localhost:5432`.
- Na nuvem a inferência pode subir antes de o worker aplicar o esquema, e `register_vector`
  falha sem a extensão: registre o tipo sob demanda e trate como resultado vazio.
- Healthcheck no compose: `pg_isready -h 127.0.0.1` (pelo socket ele responde "pronto" ainda
  durante a inicialização).
- Postgres 17 nos dois ambientes (imagem `pg17`; `postgresMajorVersion: "17"` no Blueprint,
  que não pode ser alterado depois).
- O banco gratuito expira em 30 dias e não tem backup: citar nos trade-offs.
- Defina `statement_timeout` ou equivalente: toda chamada tem tempo-limite.
