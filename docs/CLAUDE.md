# docs/

| Arquivo | Regra |
|---------|-------|
| `edital-c3a2.md` | fonte maior da verdade. **Não editar.** |
| `ebook.md` | material do professor. **Não editar.** Grande: leia por trecho (`grep -n '^## Aula'`) |
| `implementacao.md` | diário do projeto; atualize ao fim de cada tarefa |
| `trade-offs.md` | criar na Tarefa 10 |

## implementacao.md

Alguém (humano ou agente) precisa entender, no fim, **como se pensou** até o resultado.
Para cada tarefa: o que foi feito; decisões, alternativas descartadas e motivo (ligando às
aulas); problemas encontrados; como foi verificado (comando e resultado real); o que o
advisor apontou e o que mudou; desvios do plano. Acrescente, não reescreva a história: se uma
decisão mudar, registre a nova e o porquê. Atualize também a tabela de resumo.

## trade-offs.md (R7: curto)

- **CAP:** consistência eventual entre gravação e busca; o que acontece com partição entre
  worker e banco, ou sem Redis; fila sem persistência no plano gratuito; rate limit que libera
  quando o Redis cai.
- **Custo:** o que é gratuito, os limites que apertam primeiro e quanto custaria removê-los.
- **Latência:** síncrono contra assíncrono, saltos de rede entre URLs públicas, cold start,
  banco suspenso. Com **números medidos**.
