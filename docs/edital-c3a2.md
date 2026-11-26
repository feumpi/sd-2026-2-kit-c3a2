---
# ---------------------------------------------------------------------------
# METADADOS (adicionados na conversão; não fazem parte do texto original)
# ---------------------------------------------------------------------------
documento: edital_trabalho
id: C3.A2
titulo: "Plataforma de IA como Serviço (projeto integrador cloud-native)"
disciplina: "Sistemas Distribuídos e Computação em Nuvem"
professor: "Prof. M.Sc. Howard Roatti"
contato_professor: "howardcruzroatti@gmail.com"
valor_pontos: 5.0
datas:
  ultima_atualizacao_edital: 2026-08-01
  prazo_envio_grupos: 2026-11-05
  entrega: 2026-11-26        # Aula 17 — véspera do ENADE
penalidade_atraso: "-0,5 ponto por dia"
avaliacao_substitutiva: false
apresentacao_oral: false
formacao_grupos: "livre (inclusive individual)"
linguagem_padrao: python      # outra linguagem somente com acordo prévio do professor
kit_de_partida: "https://github.com/howardroatti/sd-2026-2-kit-c3a2"
forma_de_entrega: "link do repositório GitHub no AVA"
idioma: pt-BR
fonte: "Edital_-_C3.A2_-_Plataforma_de_IA_como_Serviço_projeto_integ.docx"
nota_conversao: >
  O texto do edital (seções 'Cabeçalho' a 'Roteiro sugerido de execução') foi
  preservado integralmente, alterando apenas a formatação para Markdown.
  O front matter YAML e o 'Anexo A' ao final são metadados adicionados para
  orientar um agente de IA e NÃO fazem parte do edital original. Em caso de
  divergência, prevalece o texto original.
---

<!-- ========================= INÍCIO DO TEXTO ORIGINAL ========================= -->

# Trabalho C3.A2 — Plataforma de IA como Serviço (projeto integrador cloud-native)

Disciplina: Sistemas Distribuídos e Computação em Nuvem

Prof. M.Sc. Howard Roatti · Valor: 5,0 pontos · Entrega: 26/11/2026 (Aula 17) — véspera do ENADE

*Última atualização: 01/08/2026*

*Este é o projeto que fecha o semestre. Você vai pegar tudo o que construiu e transformar em uma plataforma de verdade: conteinerizada, publicada na internet, observável e protegida. Ao final, você terá um sistema distribuído completo e público — material de portfólio para entrevista de emprego.*

## Edital

*Leia todo o edital antes de começar. Só será corrigido o trabalho que seguir estas orientações; caso contrário, a avaliação será desconsiderada.*

### 0 — Formação de grupos
<!-- req-id: R0 -->

Formação de grupos é LIVRE (inclusive individual). Se optar por grupo, envie os nomes dos componentes ao professor até 05/11/2026 no endereço howardcruzroatti@gmail.com.

### 1 — Tema
<!-- req-id: R1 -->

O tema é fixo: transformar o serviço de IA em uma PLATAFORMA cloud-native completa — conteinerizada, publicada na nuvem, observável e protegida. É o projeto integrador que reúne todo o semestre.

### 2 — Arquitetura
<!-- req-id: R2 | obrigatório -->

Arquitetura em microsserviços: API Gateway + serviço de inferência + worker de fila + armazenamento vetorial.

### 3 — Conteinerização e orquestração
<!-- req-id: R3 | obrigatório -->

Conteinerização e orquestração:

- um Dockerfile por serviço;
- um docker-compose que sobe o sistema inteiro com UM comando.

### 4 — Deploy
<!-- req-id: R4 | obrigatório -->

Deploy em nuvem (free tier) com URL pública acessível.

### 5 — Resiliência e observabilidade
<!-- req-id: R5 | obrigatório -->

Resiliência (tempo-limite, retentativa e circuit breaker) e observabilidade (rastreamento distribuído cobrindo gateway, fila e worker).

### 6 — Segurança e conformidade
<!-- req-id: R6 | obrigatório -->

Segurança e conformidade:

- autenticação por JWT no gateway e HTTPS no serviço publicado;
- seção no README informando quais dados são tratados, com qual finalidade e por quanto tempo (LGPD).

### 7 — Relatório de trade-offs
<!-- req-id: R7 | obrigatório -->

Relatório curto de trade-offs, abordando CAP, custo e latência.

### 8 — Extensões opcionais
<!-- req-id: R8 | opcional | não vale nota extra -->

Extensões opcionais (não valem nota extra, mas enriquecem o trabalho e o seu portfólio):

- Autoescalonamento (aumentar workers conforme o tamanho da fila).
- Um componente serverless ou executado na borda.
- Pipeline de CI/CD que publica automaticamente a cada commit.
- Painel de métricas do sistema.
- Manifests de Kubernetes (mesmo sem executá-los em cluster real).

### 9 — Entregáveis
<!-- req-id: R9 | obrigatório -->

Entregáveis:

- Todo o código no repositório do GitHub do grupo, organizado em diretórios (não compactado).
- README explicando a arquitetura e como executar o projeto do zero.
- No AVA, poste APENAS o link do repositório do GitHub (se o AVA exigir arquivo, envie um documento com o link).
- Entrega no repositório, SEM apresentação oral.

### 10 — Distribuição da pontuação
<!-- req-id: R10 -->

Distribuição da pontuação (total 5,0):

| **Nota** | **Critério**                                       | **O que se avalia**                                                        |
|----------|----------------------------------------------------|----------------------------------------------------------------------------|
| **1,5**  | Arquitetura e decomposição em serviços             | Arquitetura: microsserviços orquestrados por docker-compose.               |
| **1,5**  | Comunicação funcionando (REST / gRPC / mensageria) | Comunicação: gateway roteando + fila/worker; deploy público funcionando.   |
| **1,0**  | Resiliência e tratamento de falhas                 | Resiliência: tempo-limite, retentativa, circuit breaker e observabilidade. |
| **1,0**  | Execução reproduzível (README, container, deploy)  | Execução: sobe do zero com um comando; URL pública no ar; README completo. |
| **5,0**  | **TOTAL**                                          | *Sofisticação do modelo de IA NÃO pontua.*                                 |

*A qualidade ou a sofisticação do modelo de IA NÃO compõe a nota. A inteligência artificial é a carga de trabalho do sistema, não o objeto de avaliação. Todo contato com IA neste trabalho é chamada de biblioteca ou de API: não é necessário treinar modelos nem dominar matemática de aprendizado de máquina.*

### 11 — Kit de partida
<!-- req-id: R11 -->

Kit de partida: https://github.com/howardroatti/sd-2026-2-kit-c3a2

- Faça um fork (cópia) do kit e estude-o ANTES de começar o seu projeto.
- O modelo de IA já vem pronto; concentre o esforço na engenharia distribuída.
- Não deixe para a última hora: o projeto cresce ao longo do bloco.
- Não serão aceitos projetos idênticos ou cópias parciais.

## Observações importantes

- Se for em grupo, todos os componentes devem participar do desenvolvimento; membros que não contribuírem podem ter a nota individual ajustada.
- O trabalho NÃO possui avaliação substitutiva.
- Atrasos serão tolerados, porém com perda de 0,5 ponto por dia de atraso.
- Mantenha o GitHub atualizado com commits ao longo do período (e não um único commit no final).

## FAQ — Perguntas Frequentes

**Preciso saber machine learning?**

Não. O modelo já vem pronto e configurado no kit. Todo contato com IA é chamada de biblioteca ou de API — você não treina modelos nem precisa de matemática de ML.

**Preciso de internet ou GPU no laboratório?**

Não. O kit funciona 100% offline: o modelo é treinado localmente (scikit-learn) e o cliente de LLM tem modo simulado quando não há chave de API.

**O trabalho é em grupo?**

Grupos livres, a critério de vocês — inclusive individual. Se optarem por grupo, todos os componentes devem participar do desenvolvimento.

**Tem apresentação?**

Não. A entrega é no repositório do GitHub, sem apresentação oral. A avaliação recai sobre o sistema funcionando, a arquitetura e as decisões de projeto.

**Posso usar IA para me ajudar a programar?**

Sim, é realista e permitido. O que se avalia é o sistema funcionando e as decisões de arquitetura — que você precisa saber explicar.

**Posso usar outra linguagem?**

O kit é em Python porque é o ecossistema usado nas aulas. Se quiser outra linguagem, combine com o professor antes de começar.

**Existe avaliação substitutiva para o trabalho?**

Não. O trabalho não possui avaliação substitutiva.

**E se eu atrasar a entrega?**

Atrasos serão tolerados, porém com perda de 0,5 ponto por dia de atraso.

## Roteiro sugerido de execução

1. Publique cedo, ainda que incompleto: deploy sempre dá mais trabalho do que se imagina.
2. Externalize TODA configuração em variáveis de ambiente — o container precisa ser portátil.
3. Teste o comando único do zero em outra máquina antes de entregar.
4. Revise os logs: nenhum dado pessoal pode estar sendo gravado.

*Antes de entregar: apague a pasta do projeto, clone do zero e siga o SEU próprio README. Se funcionar, está pronto para entrega.*

<!-- ========================== FIM DO TEXTO ORIGINAL =========================== -->

---

## Anexo A — Índice de requisitos para agentes de IA (metadado adicionado)

> **Atenção:** este anexo NÃO faz parte do edital original. É apenas uma
> reorganização do conteúdo acima em formato de checklist, para facilitar o
> planejamento e a verificação por um agente. Cada item aponta para a seção de
> origem. Em caso de divergência, prevalece o texto original.

### A.1 Requisitos obrigatórios

| ID | Requisito (resumo) | Origem | Critério de nota relacionado |
|----|--------------------|--------|------------------------------|
| R2.1 | Serviço **API Gateway** | §2 | Arquitetura (1,5) |
| R2.2 | **Serviço de inferência** | §2 | Arquitetura (1,5) |
| R2.3 | **Worker de fila** | §2 | Arquitetura (1,5) / Comunicação (1,5) |
| R2.4 | **Armazenamento vetorial** | §2 | Arquitetura (1,5) |
| R3.1 | Um `Dockerfile` por serviço | §3 | Arquitetura (1,5) / Execução (1,0) |
| R3.2 | Um `docker-compose` que sobe o sistema inteiro com UM comando | §3 | Arquitetura (1,5) / Execução (1,0) |
| R4.1 | Deploy em nuvem (free tier) com URL pública acessível | §4 | Comunicação (1,5) / Execução (1,0) |
| R5.1 | Tempo-limite (timeout) | §5 | Resiliência (1,0) |
| R5.2 | Retentativa (retry) | §5 | Resiliência (1,0) |
| R5.3 | Circuit breaker | §5 | Resiliência (1,0) |
| R5.4 | Rastreamento distribuído cobrindo gateway, fila e worker | §5 | Resiliência (1,0) |
| R6.1 | Autenticação por JWT no gateway | §6 | — (requisito do edital) |
| R6.2 | HTTPS no serviço publicado | §6 | — (requisito do edital) |
| R6.3 | Seção LGPD no README: dados tratados, finalidade e prazo de retenção | §6 | Execução (1,0) — README completo |
| R7.1 | Relatório curto de trade-offs: CAP, custo e latência | §7 | — (requisito do edital) |
| R9.1 | Código no GitHub do grupo, organizado em diretórios, não compactado | §9 | Execução (1,0) |
| R9.2 | README com arquitetura e como executar do zero | §9 | Execução (1,0) |
| R9.3 | Gateway roteando + fila/worker funcionando (REST / gRPC / mensageria) | §10 | Comunicação (1,5) |
| R11.1 | Partir de um fork do kit de partida | §11 | — |
| OBS.1 | Histórico de commits ao longo do período (não um único commit final) | Observações | — |

### A.2 Restrições e diretrizes

- A sofisticação do modelo de IA **não** pontua; o modelo já vem no kit (§10, §11, FAQ).
- Linguagem padrão: Python; outra linguagem só com acordo prévio do professor (FAQ).
- Toda configuração externalizada em variáveis de ambiente (Roteiro, item 2).
- Nenhum dado pessoal pode ser gravado em logs (Roteiro, item 4).
- O kit funciona offline; o cliente de LLM tem modo simulado sem chave de API (FAQ).
- Não são aceitos projetos idênticos ou cópias parciais (§11).

### A.3 Opcionais (sem nota extra) — §8

- [ ] Autoescalonamento de workers conforme tamanho da fila
- [ ] Componente serverless ou na borda
- [ ] Pipeline de CI/CD com publicação automática a cada commit
- [ ] Painel de métricas
- [ ] Manifests de Kubernetes

### A.4 Critério de pronto (derivado do texto final do edital)

1. Apagar a pasta do projeto.
2. Clonar o repositório do zero.
3. Seguir apenas o README do próprio projeto.
4. O sistema sobe com um único comando e a URL pública responde.
