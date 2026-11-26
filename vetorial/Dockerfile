# Armazenamento vetorial: Postgres 17 com a extensao pgvector (build a partir da raiz).
FROM pgvector/pgvector:pg17

# executado pela imagem oficial na primeira inicializacao do volume
COPY vetorial/esquema.sql /docker-entrypoint-initdb.d/01-esquema.sql
