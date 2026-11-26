-- Armazenamento vetorial: documentos processados pelo worker (idempotente).
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documentos (
    id         text PRIMARY KEY,           -- sha256(origem + texto)
    origem     text NOT NULL,
    texto      text NOT NULL,
    sentimento text NOT NULL,
    confianca  real NOT NULL,
    vetor      vector(512) NOT NULL,       -- mesma dimensao de inferencia/embeddings.py
    criado_em  timestamptz NOT NULL DEFAULT now()
);
