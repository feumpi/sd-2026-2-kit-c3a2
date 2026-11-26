# Publicação no plano gratuito (Render + Honeycomb)

O [render.yaml](../render.yaml) (Blueprint) cria 3 web services, 1 Postgres e 1 Key Value,
todos no plano `free`.

## Antes de começar

- Fork do repositório no GitHub e conta no [Render](https://render.com) com acesso a ele.
- Conta no [Honeycomb](https://ui.honeycomb.io) (região US) e uma chave do tipo **Ingest**.
- O Render permite **um** Postgres e **um** Key Value gratuitos por *workspace*.

## Passos

1. **URLs entre os serviços.** No `render.yaml`, `URL_INFERENCIA` e `URL_WORKER` são fixas. Numa
   instalação nova, o Render pode acrescentar um sufixo aos nomes: crie o Blueprint, anote as
   URLs de `c3a2-inferencia` e `c3a2-worker`, atualize os três valores no arquivo e faça
   `push`. A referência automática à `RENDER_EXTERNAL_URL` de outro serviço trava a
   sincronização.
2. No painel: **New → Blueprint**, escolha o repositório e a branch `main`.
3. Preencha os campos pedidos (eles não ficam no repositório):

   | Variável | Serviço | Valor |
   |----------|---------|-------|
   | `USUARIO_DEMO`, `SENHA_DEMO` | gateway | usuário e uma senha forte e exclusiva |
   | `OTEL_EXPORTER_OTLP_HEADERS` | gateway, inferência e worker | `x-honeycomb-team=<chave>` |

4. **Apply.** `JWT_SEGREDO` e `TOKEN_INTERNO` são gerados pelo Render.
   Depois, confira em **Environment** de cada serviço se as variáveis do passo 3 existem. No
   primeiro deploy deste projeto, em que a sincronização travou e foi substituída, elas ficaram
   ausentes e precisaram ser criadas à mão (**Save and deploy**). Sem elas o login responde 401.
5. Cada `push` na `main` republica os serviços afetados (`buildFilter`; arquivos `.md` não
   disparam *build*).

## Conferir

```bash
URL_BASE=https://<gateway>.onrender.com E2E_CREDENCIAIS=<arquivo> uv run pytest -m e2e
URL_BASE=https://<gateway>.onrender.com E2E_CREDENCIAIS=<arquivo> \
  INTERVALO_CONSULTA=1 uv run python deploy/medir_latencia.py --amostras 5
```

`<arquivo>` tem as linhas `USUARIO_DEMO=...` e `SENHA_DEMO=...` e fica fora do repositório.
No Honeycomb, um `POST /documentos` aparece como um único trace entre os três serviços. Um erro
`401` do exportador no log indica chave inválida ou de outra região.

## Limites do plano gratuito

- Serviços dormem após 15 minutos sem tráfego e levam até cerca de um minuto para voltar.
- Neste projeto, um serviço adormecido **não acordou com chamadas de outro serviço**, só com
  acesso externo: abra a raiz do gateway no navegador (ela acorda os demais) ou chame o
  `/saude` dos três.
- As 750 horas mensais são compartilhadas pelo *workspace*.
- O Postgres expira 30 dias depois de criado (mais 14 de carência) e não tem backup.
- O Key Value não persiste: um reinício apaga a fila.
