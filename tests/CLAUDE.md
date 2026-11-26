# tests/

`uv run pytest` roda os unitários; `uv run pytest -m e2e` exige o compose no ar (o marcador
já vem desligado por padrão no `pyproject.toml`).

- Unitários: sem rede, Docker ou chave de API. `TestClient`, `fakeredis`, `monkeypatch` em
  `requests`, `time.sleep`/`time.time` simulados, repositório do banco substituído.
- `test_ambiente.py` é a sanidade das dependências: mantenha-o passando e acrescente a nova
  dependência à lista.
- Um arquivo por área (`test_gateway_auth.py`, `test_worker.py`, …), escrito na mesma tarefa
  do código.
- Modelos prontos do C2 em `referencia/c2a2/tests/` (disjuntor, retentativa, fila, DLQ,
  busca, e2e com `docker compose stop`). Adapte os imports.
- Crie um `conftest.py` que force LLM simulado, exporter desligado e segredos de teste. Vários
  módulos importados leem o ambiente **no import**: use `monkeypatch.setattr` no atributo.
- Cubra os riscos do projeto: propagação do `traceparent` pela mensagem; logs sem texto nem IP
  (`caplog`); falha transitória não indo à dead-letter; 4xx não abrindo o disjuntor; vetor
  zero; expurgo por retenção.
