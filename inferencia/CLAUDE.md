# inferencia/ — serviço de IA (porta 8001)

Único lugar com modelo, embeddings e LLM. **A qualidade da IA não pontua**: não troque nem
"melhore" o modelo.

| Arquivo | Origem | O que fazer |
|---------|--------|-------------|
| `modelo.py` | C1 (do kit), sem alteração | usar como está |
| `embeddings.py` | C2, sem alteração | trocar TF-IDF por `HashingVectorizer` de dimensão fixa |
| `llm.py` | C2, sem alteração | usar como está (modo simulado sem `LLM_API_KEY`) |
| `app.py` | criar | rotas abaixo |

## Rotas (todas exigem `X-Token-Interno`, menos `/saude`)

| Rota | Entrada → saída |
|------|-----------------|
| `POST /predict` | `{texto}` → resultado do modelo |
| `POST /processar` | `{texto}` → `{sentimento, confianca, vetor}` (usada pelo worker) |
| `POST /buscar` | `{pergunta, top_k}` → `{resultados: [{origem, texto, sentimento, score}]}` |
| `POST /perguntar` | `{pergunta}` → `{resposta, contexto, fontes}` |
| `GET /saude` | status, modelo carregado, modo do LLM, estado do disjuntor |

- Carregar o modelo **uma vez**, na subida (Aula 6).
- `modelo.py` treina e grava `modelo.joblib` na própria pasta: execute
  `python -m inferencia.modelo` **no build da imagem**, senão o usuário sem privilégios não
  consegue gravar e o cold start fica mais lento.
- `modelo.prever` devolve o `texto` junto: nunca registre o retorno em log.

## Embeddings

`HashingVectorizer(n_features=512, ngram_range=(1, 2), norm="l2")`: sem `fit`, mesma dimensão
sempre, offline. Mantenha `vetorizar(texto) -> list[float]` (`ajustar` deixa de existir).
Texto sem tokens gera vetor zero, e a distância de cosseno do pgvector dá `NaN`: recuse (422)
ao processar e devolva lista vazia ao buscar.

## Busca e RAG

- A busca é feita no banco (ver `vetorial/CLAUDE.md`); descarte `score <= 0`.
- Sem trecho relevante: responda que não há base, sem chamar o LLM.
- LLM com tempo-limite (`LLM_TIMEOUT`), retentativa e disjuntor. Falha → 503 com
  `Retry-After`, **trechos e fontes** (degradação elegante).
- Banco fora do ar → 503. Tabela ainda inexistente → resultado vazio.
- Leitura apenas: este serviço nunca grava no banco.
