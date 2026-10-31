# Proposta de Arquitetura: Observabilidade Própria na AWS

## 1. Objetivo

Criar uma plataforma própria de observabilidade na AWS, sem depender de Datadog, New Relic ou outra ferramenta SaaS, para:

- Centralizar **logs** de todas as pontas da aplicação e infraestrutura.
- Disponibilizar **Live Tail** de logs no Grafana.
- Instrumentar os backends REST com **distributed tracing**.
- Visualizar cada requisição como uma **trace**, com waterfall por camadas: controller, service, repository, banco de dados e chamadas externas.
- Correlacionar logs e traces por meio do `trace_id`.
- Coletar **métricas** de aplicação e JVM e derivar das traces as métricas RED e o service graph, completando os três pilares (logs, traces e métricas).

A solução utiliza principalmente serviços gerenciados da AWS e componentes open source: **Amazon S3**, **Amazon CloudWatch Logs**, **Grafana Loki**, **Grafana Tempo**, **Grafana Alloy**, **Grafana Mimir**, **Fluent Bit** e uma **EC2 com Docker Compose** para hospedar a stack de observabilidade.

---

## 2. Log x Trace

Embora sejam complementares, **log** e **trace** respondem a perguntas diferentes.

### Log

Um **log** é um registro pontual de um evento.

Exemplos:

- Uma requisição HTTP falhou.
- Uma exception foi lançada.
- Uma query demorou mais do que o esperado.
- O WAF bloqueou uma requisição.
- Um container reiniciou inesperadamente.

Um log normalmente responde à pergunta:

> “O que aconteceu, quando aconteceu e com quais detalhes?”

Logs são úteis para depuração, auditoria, alertas e acompanhamento em tempo real.

### Trace

Uma **trace** representa o caminho completo de uma requisição através da aplicação.

Ela é composta por vários **spans**. Cada span representa uma etapa ou operação, por exemplo:

- Recebimento da requisição HTTP no controller.
- Execução de um método de service.
- Execução de uma query no repository.
- Chamada para outro microsserviço.
- Consulta ao banco de dados.

Uma trace responde à pergunta:

> “Por onde essa requisição passou, quanto tempo cada etapa levou e onde está o gargalo?”

### Exemplo visual

```text
GET /api/pedidos/123                                  180 ms
└── meu-backend
    ├── PedidoController.buscarPedido                  175 ms
    ├── PedidoService.buscarPedido                     170 ms
    │   ├── PedidoRepository.findById                   22 ms
    │   │   └── SELECT * FROM pedidos WHERE id = ?      20 ms
    │   └── EstoqueService.reservarEstoque            120 ms
    │       └── POST /estoque/reservar                115 ms
    └── PagamentoService.autorizar                     15 ms
```

### Relação entre os dois

A correlação acontece pelo `trace_id`.

Toda linha de log gerada durante uma requisição deve conter o mesmo `trace_id` da trace correspondente. Assim, é possível:

- Ver um erro no Loki.
- Clicar no `trace_id`.
- Abrir a trace completa no Tempo.
- Identificar exatamente qual etapa ficou lenta ou falhou.
- Voltar aos logs daquele span específico.

---

## 3. Visão geral da arquitetura

A arquitetura separa **logs**, **traces** e **métricas** em pipelines distintos, porque possuem padrões de ingestão, armazenamento e consulta diferentes.

```text
Requisição:  Usuário ──> WAF ──> ALB ──> nginx ──> Backends REST x4 (EC2) ──> RDS

Logs:        Backends ──> Fluent Bit ──(HTTP, API do Loki)──┐
             RDS/WAF  ──> CloudWatch Logs ──(leitor)────────┴──> Alloy ──┬──> Loki ──> S3 (chunks)
                                                                         └──> S3 (arquivo bruto)

Traces:      Backends ──> Alloy ──> Tempo ──> S3

Métricas:    Backends ──> Alloy ──> Mimir ──> S3
             Tempo (metrics-generator) ──> Mimir

Consulta:    Equipe ──> ALB :3000 ──> Grafana ──> Loki / Tempo / Mimir
```

Alloy, Loki, Tempo, Mimir e Grafana rodam como containers separados em uma única **EC2 de observabilidade**, com Docker Compose.

O Grafana consulta o Loki, o Tempo e o Mimir (a stack LGTM: Loki, Grafana, Tempo, Mimir); o S3 fica atrás dos três, nunca entre eles e o Grafana. O ALB faz parte do caminho da requisição, mas não é fonte de logs (ver seção 12).

### Decisões principais

| Decisão | Justificativa |
|---|---|
| Sem barramento de logs | O Fluent Bit envia direto ao Alloy, e a durabilidade vem do buffer em disco do Fluent Bit. Um barramento na mesma EC2 do consumidor cairia junto com ele e não protegeria nada. Kinesis (com Logstash) e Redpanda foram avaliados e descartados |
| Alloy como ponto único de processamento de logs | Coletor da própria Grafana, sem JVM nem plugins extras: recebe os logs dos containers e os de RDS/WAF pela API de push do Loki, define labels e timestamp e grava no Loki e no arquivo bruto. O Loki, sem autenticação, não fica exposto aos nós app |
| Leitor próprio de RDS e WAF no CloudWatch (polling) | Sem Subscription Filter, Kinesis ou Lambda. Troca algum atraso (polling de 15 s mais a entrega ao CloudWatch, seção 4.5) por menos infraestrutura. Substitui o `otelcol.receiver.awscloudwatch`, que perdeu eventos atrasados no lab (seção 4.3) |
| Arquivo bruto no S3 pelo Alloy | Os chunks do Loki só são legíveis pelo Loki. O Alloy grava as linhas originais por origem, consultáveis pelo Athena (seção 4.4) |
| Tempo para traces | Backend open source de tracing, com armazenamento em S3 e integração nativa com Grafana |
| Alloy também para traces e métricas, sem OTel Collector | Um só coletor para os três sinais: recebe o OTLP dos backends (`:4318`), descarta os spans de health check, envia traces ao Tempo e métricas ao Mimir, com fila e retry nos exporters durante reinícios, e é onde entraria tail sampling. Em troca, um restart do Alloy interrompe os três sinais ao mesmo tempo, e a flag `--stability.level=experimental` (exigida pelos componentes de logs) vale para o processo todo (seção 6.6) |
| Loki para logs | Armazenamento barato em S3 e Live Tail nativo no Grafana |
| Mimir para métricas | Fecha a stack LGTM: os três backends guardam no S3 com o mesmo modelo. Recebe métricas por remote write (push), sem precisar descobrir os containers dos backends, e responde PromQL; integração nativa com Grafana e com o metrics-generator do Tempo. Monolítico, na arquitetura clássica (sem Kafka) |
| Stack de observabilidade em uma EC2 com Docker Compose | Os componentes conversam pela rede Docker do Compose, dentro da EC2; os backends alcançam o Alloy pelo IP privado fixo da EC2. Nenhum balanceador ou service discovery entre eles (o lab bloqueia Cloud Map). Mesmo padrão EC2 + Ansible + Docker já usado no projeto |
| Cada componente em seu próprio container | Deploy e restart independentes, com limite de memória por container |
| Grafana exposto pelo `main-alb` existente | Listener `:3000` restrito aos IPs da equipe; a EC2 fica em subnet privada, sem IP público |
| Sem ingestão de access logs do ALB | O ALB possui apenas regras simples de roteamento e balanceamento; logs de aplicação e traces já cobrem a investigação principal |

---

## 4. Pipeline de logs

### 4.1 Fontes de logs

| Origem | Como os logs são gerados | Caminho até o Alloy |
|---|---|---|
| Containers EC2 (`app`, `nginx`, `rabbitmq`) | Driver `fluentd` do Docker envia ao Fluent Bit (já instalado) | Fluent Bit → Alloy (push HTTP, API do Loki) |
| RDS | Logs exportados nativamente para CloudWatch Logs | `cloudwatch-reader` lê o log group (polling) |
| AWS WAF | Logs exportados para CloudWatch Logs, com prefixo `aws-waf-logs-` | `cloudwatch-reader` lê o log group (polling) |

### 4.2 Fluxo dos containers

O Fluent Bit já roda no Docker Swarm (`fluent/fluent-bit:3.2`, nós manager), configurado pelo Ansible em `DevOps/prod/ansible/roles/app/templates/fluent-bit.conf.j2`. Os containers `app`, `nginx` e `rabbitmq` usam o logging driver `fluentd`, que entrega cada linha ao Fluent Bit (input `forward`, porta 24224) com a tag do serviço.

O Fluent Bit:

1. Recebe os logs via `forward` (campo `log` com a linha original).
2. Faz parse da linha como JSON quando possível (filtro `parser`, `reserve_data on`); linhas em texto passam intactas.
3. Adiciona `env`, `host` e `origin=container-logs` (filtro `record_modifier`).
4. Copia a tag (`app`, `nginx`, `rabbitmq`) para o campo `service` (filtro `lua`).
5. Envia ao Alloy pelo output `loki` (HTTP, API de push do Loki) no IP privado fixo da EC2 de observabilidade, porta `3500`. `env`, `origin`, `service` e `host` viram labels (`label_keys`), e o registro inteiro vai em JSON como linha (`line_format json`), com esses campos incluídos, para que o arquivo bruto e o `| json` do Loki os tenham.

O horário do evento é o timestamp do próprio registro no Fluent Bit (o do driver `fluentd`), que segue na requisição de push. O `time_key` deixa de ser necessário. O driver precisa de `fluentd-sub-second-precision: "true"` (no `x-fluentd` do `docker-compose.yml.j2`): sem isso, ele trunca o horário no segundo, e as linhas do mesmo segundo perdem a ordem no Loki.

```ini
[SERVICE]
    flush        1
    storage.path /fluent-bit/buffer
    # Espera máxima entre retentativas (padrão 2000 s)
    scheduler.cap 60

[INPUT]
    name         forward
    storage.type filesystem

[OUTPUT]
    name        loki
    match       *
    # Mesmo IP fixo da EC2 de observabilidade
    host        {{ otel_endpoint_ip }}
    port        3500
    label_keys  $env,$origin,$service,$host
    line_format json
    retry_limit no_limits
    storage.total_limit_size 1G
```

**Buffer em disco:** volta o volume `fluent-bit-buffer` (`storage.path`), com `storage.type filesystem` no input. Enquanto o Alloy ou a EC2 de observabilidade estiverem fora do ar, os chunks se acumulam no disco do nó app e são reenviados quando o destino volta, com o horário original. `retry_limit no_limits` evita o descarte após 1 falha (padrão do Fluent Bit). Limites: ao atingir `storage.total_limit_size`, os chunks mais antigos são descartados, e se o nó app morrer o buffer dele vai junto.

Requisitos: liberar a porta `3500` no security group da EC2 de observabilidade para as EC2 de app (seção 6.3). O Fluent Bit não chama mais nenhuma API da AWS, então não precisa de permissão IAM.

**Feito no repo DevOps (testado localmente em 2026-10-26 com Fluent Bit 3.2 e Alloy):**
- `fluent-bit.conf.j2` com o output `loki`, o buffer em disco e `scheduler.cap`.
- O volume `fluent-bit-buffer` de volta e o `fluentd-sub-second-precision` no `docker-compose.yml.j2`.
- `kinesis_stream` trocada por `otel_endpoint_ip` em `terraform/ansible.tf`.
- A nova variável `otel_endpoint_ip`, sem default, em `variables.tf`.

Resultados do teste:
- As 4 labels chegaram ao `loki.source.api` e o `trace_id` ficou na linha.
- Com o Alloy parado, o log ficou em disco e foi entregue quando ele voltou, com o horário original em milissegundos.

**Logs do backend em JSON:** hoje o backend usa o pattern padrão do Spring (texto). Como o projeto está em Spring Boot 4, basta uma linha em `application-prod.properties` para ativar o structured logging nativo, que já inclui o MDC (`trace_id`, `span_id` do OTel Agent e o `usuario` atual):

```properties
logging.structured.format.console=logstash
```

### 4.3 Fluxo de RDS e WAF

RDS e WAF já exportam para o CloudWatch Logs. Um leitor próprio ([`cloudwatch-reader/`](cloudwatch-reader/), Python e boto3, um container no Compose) lê os log groups pela API do CloudWatch e envia ao Alloy pela API de push do Loki, sem Subscription Filter, Kinesis ou Lambda.

```text
RDS ──> CloudWatch Logs <──(polling, 15 s)── cloudwatch-reader ──(:3501)──> Alloy
WAF ──> CloudWatch Logs <──(polling, 15 s)── cloudwatch-reader ──(:3502)──> Alloy
```

- **Por que não o `otelcol.receiver.awscloudwatch`:** ele não tem margem para eventos que chegam atrasados ao CloudWatch e perdeu eventos no lab; um restart relê o log group inteiro; e uma falha no STS derruba o processo do Alloy (task 2.4).
- Log groups por nome, com a origem fixa na config:
  - `/aws/rds/instance/app-db/error` e `/slowquery` → `origin="rds-logs"`
  - `aws-waf-logs-main-alb-waf` → `origin="waf-logs"`
- **Eventos atrasados:** cada ciclo relê uma janela recente (`lookback_seconds`: 120 s no WAF, que entrega em até 24 s; 600 s no RDS, em que o error log levou até 141 s) e descarta pelo `eventId` o que já enviou. Um evento que atrase mais que a janela não é lido.
- **Retomada:** o progresso e os IDs enviados ficam em um volume no EBS. Depois de uma parada, o leitor continua de onde estava e avança no máximo 15 min por ciclo em todos os grupos, porque o Loki recusa o que tiver mais de 1 h em relação ao log mais novo do stream. Se o volume for perdido, ele recomeça na última 1 h.
- **Timestamp:** o Alloy recebe o horário do evento no CloudWatch, com `use_incoming_timestamp = true`.
- **Falhas:** um grupo que falha não avança nem impede os outros, e o próximo ciclo relê a janela dele. O throttling da API espera em vez de falhar (retentativa `adaptive` do boto3).
- **Volume:** reler a janela custa chamadas à API e tráfego no NAT, proporcionais ao volume de logs. A ~237 req/s por 1 min, o leitor não perdeu eventos, chegou a 83 MiB e os ciclos subiram para até ~26 s, sem erro de throttling (task 2.4).
- **Sem métricas próprias:** o leitor só registra no stdout (`docker compose logs cloudwatch-reader`).
- **IAM:** só `logs:FilterLogEvents`, pela `LabRole`.

### 4.4 Processamento no Alloy e envio ao Loki

O **Alloy** roda em container na EC2 de observabilidade e é o único ponto de processamento de logs:

1. Recebe os logs dos containers em `loki.source.api` (porta `3500`), com `use_incoming_timestamp = true`. O padrão é `false`, e com ele os logs reenviados do buffer do Fluent Bit entrariam com o horário da chegada.
2. Recebe RDS e WAF do `cloudwatch-reader` em dois `loki.source.api` (portas `3501` e `3502`, só na rede do Compose), um por origem para separar o arquivo bruto (seção 4.3).
3. Mantém só quatro labels: `env`, `origin`, `service` e `host`. Nos containers, elas chegam prontas do Fluent Bit; em RDS e WAF, do `cloudwatch-reader`.
4. Envia ao Loki por `loki.write` (`http://loki:3100`, rede do Compose).
5. Grava o arquivo bruto no S3 (abaixo).

**Labels x linha:** `trace_id`, `span_id`, `usuario`, `level` e os demais campos da aplicação ficam **na linha**, nunca em labels. Como labels, explodiriam a cardinalidade do Loki e quebrariam o derived field do `trace_id` (seção 5.6). Na linha, ficam filtráveis com `| json`.

```alloy
loki.source.api "fluentbit" {
  http {
    listen_address = "0.0.0.0"
    listen_port    = 3500
  }
  use_incoming_timestamp = true
  // otelcol.receiver.loki "raw" leva ao arquivo bruto (abaixo)
  forward_to = [loki.write.default.receiver, otelcol.receiver.loki.raw.receiver]
}

loki.write "default" {
  endpoint {
    url                 = "http://loki:3100/loki/api/v1/push"
    max_backoff_retries = 0 // tenta indefinidamente enquanto o Loki reinicia
  }
}
```

**Retentativas:** por padrão, o `loki.write` tenta 10 vezes (backoff de 500 ms a 5 min) e depois **descarta** (`loki_write_dropped_bytes_total`). Com `max_backoff_retries = 0`, ele tenta até o Loki voltar. O que estiver pendente fica em memória no Alloy, então um restart do próprio Alloy perde esses registros. O WAL do `loki.write` resolveria, mas é experimental e fica desligado. É um risco aceito: a janela é a de um restart, já que, com o Alloy fora do ar, quem acumula é o buffer em disco do Fluent Bit.

**Arquivo bruto:** `otelcol.receiver.loki` → `otelcol.exporter.awss3` (experimental) grava no bucket `logs-raw` com o marshaler `body`, ou seja, só a linha original. Há um prefixo por origem (`origin=container-logs/`, `origin=waf-logs/`, `origin=rds-logs/`) e o particionamento padrão por tempo (`year=/month=/day=/hour=/minute=`). Containers e WAF ficam em JSON por linha, e RDS em texto, com uma tabela do Athena por origem. O marshaler `body` grava uma linha por registro (validado no lab), mas um registro de slow query do RDS tem várias linhas. Os arquivos são independentes do Loki.

O Loki persiste os logs no Amazon S3.

**Retenção:** sem configuração, o Loki nunca apaga dados e o bucket cresce sem limite.

| Dado | Onde | Retenção | Configuração |
|---|---|---|---|
| Logs no Loki | S3 `loki-logs` | 7 dias | `limits_config.retention_period: 168h`, `compactor.retention_enabled: true`, `compactor.delete_request_store: s3` |
| Arquivo bruto | S3 `logs-raw` | 30 dias | Lifecycle rule de expiração no bucket |
| Traces | S3 `tempo-traces` | 7 dias | `compactor.compaction.block_retention: 168h` no Tempo |
| Métricas | S3 `mimir-metrics` | 15 dias | `limits.compactor_blocks_retention_period: 15d` no Mimir (seção 17.1) |
| Profiles | S3 `pyroscope-profiles` | 7 dias | Retenção do Pyroscope (seção 18.4) |

### 4.5 Tráfego: protocolos e latência

| Trecho | Protocolo | Porta | Rede |
|---|---|---|---|
| Container → Fluent Bit | Fluentd Forward (msgpack sobre TCP), driver `fluentd` | 24224 | Local, no nó app |
| Fluent Bit → Alloy | HTTP `POST /loki/api/v1/push`, sem TLS | 3500 | VPC, IP privado; SG restrito às EC2 de app |
| `cloudwatch-reader` → CloudWatch Logs | HTTPS, API da AWS (polling) | 443 | NAT gateway da VPC (`ngw`) |
| Alloy → Loki | HTTP, push da API do Loki | 3100 | Rede do Compose |
| Alloy, Loki, Tempo e Mimir → S3 | HTTPS | 443 | NAT gateway; um VPC gateway endpoint de S3 (gratuito) tiraria esse tráfego do NAT, que cobra por GB processado |
| Grafana → Loki | HTTP; Live Tail por WebSocket (`/loki/api/v1/tail`) | 3100 | Rede do Compose |
| Navegador → Grafana | HTTP via `main-alb`; Live Tail por WebSocket (o ALB aceita) | 3000 | Internet, restrito aos IPs da equipe |

O trecho Fluent Bit → Alloy segue sem TLS, como o OTLP dos backends na porta `4318`: o tráfego não sai da VPC e o security group só aceita as EC2 de app.

O Fluent Bit só considera um chunk entregue quando o Alloy responde 2xx. Em caso de erro ou timeout, o chunk continua no buffer em disco e é reenviado: a entrega é **pelo menos uma vez**. Uma duplicata é possível depois de um timeout, nunca uma perda silenciosa nesse trecho.

**Latência dos logs dos containers (Live Tail):**

| Etapa | Atraso |
|---|---|
| Driver `fluentd` → Fluent Bit | milissegundos |
| `flush 1` do Fluent Bit | até 1 s |
| HTTP até o Alloy (mesma VPC, entre AZs) | ~1–2 ms |
| `batch_wait` do `loki.write` (padrão) | até 1 s |
| Loki → Grafana (tail) | menos de 1 s |
| **Total** | **~1–3 s** |

**Latência de RDS e WAF:** o atraso de entrega do próprio serviço ao CloudWatch (no lab, 7 a 24 s no WAF, ~3 s no slow query e 5 a 141 s no error log), mais até 15 s de polling e até 1 s de lote, ou seja, **até ~45 s no WAF, ~20 s no slow query e até ~2,5 min no error log do RDS**. No lab, o WAF levou de 14 a 34 s (até 43 s sob carga) e o slow query de 10 a 22 s; o valor do error log é uma estimativa (task 2.4). Esse é o custo de não ter Subscription Filter: com o Kinesis, eram segundos.

### 4.6 Live Tail

No Grafana, em **Explore → Loki**, é possível ativar o modo **Live** e acompanhar os logs conforme chegam.

Exemplos de consulta:

```logql
{env="production"}
```

```logql
{env="production", origin="container-logs"}
```

```logql
{env="production", origin="waf-logs"} |= "BLOCK"
```

```logql
{env="production"} | json | level="ERROR"
```

---

## 5. Pipeline de traces

### 5.1 Componentes

| Componente | Função |
|---|---|
| OpenTelemetry Java Agent | Instrumenta automaticamente os backends REST |
| Grafana Alloy | Recebe spans via OTLP, filtra e encaminha ao Tempo |
| Grafana Tempo | Armazena, indexa e consulta traces |
| Amazon S3 | Armazenamento durável das traces |
| Grafana | Visualização do waterfall e navegação entre traces e logs |

### 5.2 Fluxo

```text
Backend REST #1 ─┐
Backend REST #2 ─┼── OTLP ──> Alloy ──> Tempo ──> S3
Backend REST #3 ─┤
Backend REST #4 ─┘
```

Os quatro backends são idênticos e utilizam o mesmo `service.name`.

São 4 containers de backend: um Docker Swarm por AZ (`app-1` na AZ a, `app-2` na AZ b), cada um com o serviço `app` em `replicas: 2`.

Os atributos de recurso usam os **mesmos valores das labels do Loki**, para que a correlação da seção 5.6 ache os logs e para que trace e log digam o mesmo container e a mesma AZ:

| Atributo do span | Valor | Label/campo no Loki |
|---|---|---|
| `service.name` | `app` | label `service="app"` (tag do driver `fluentd`) |
| `host.name` | `app-1` / `app-2` (`inventory_hostname`) | label `host` (`record host {{ inventory_hostname }}` no Fluent Bit) |
| `cloud.availability_zone` | `a` / `b` (variável `az` do inventário) | — (`host` já identifica a AZ: `app-1` = a, `app-2` = b) |
| `service.instance.id` | `app-1-1`, `app-1-2`, `app-2-1`, `app-2-2` (host + slot do Swarm) | campo `container_name` na linha (`/stockflow_app.<slot>.<task>`, adicionado pelo driver `fluentd`) |

Variáveis no `docker-compose.yml.j2`. O Ansible renderiza o arquivo por host (`inventory_hostname`, `az`), e o Swarm preenche o slot (`{{.Task.Slot}}`, envolto em `{% raw %}` para o Jinja não interpretar):

```yaml
environment:
  JAVA_TOOL_OPTIONS: "-javaagent:/otel/opentelemetry-javaagent.jar"
  OTEL_SERVICE_NAME: app # igual à label service do Loki
  OTEL_EXPORTER_OTLP_ENDPOINT: "http://{{ otel_endpoint_ip }}:4318" # IP privado da EC2 de observabilidade
  OTEL_RESOURCE_ATTRIBUTES: "host.name={{ inventory_hostname }},cloud.availability_zone={{ az }},service.instance.id={{ inventory_hostname }}-{% raw %}{{.Task.Slot}}{% endraw %}"
```

O `OTEL_RESOURCE_ATTRIBUTES` tem precedência sobre os detectores do agente, então o `host.name` deixa de ser o ID do container.

O agente envia spans e métricas por OTLP HTTP (`http/protobuf`, padrão do agente 2.x) para o Alloy.

### 5.3 Instrumentação automática

Com o OpenTelemetry Java Agent, os seguintes pontos já são instrumentados sem alteração de código:

- Endpoints REST do Spring MVC.
- Chamadas JDBC/JPA.
- Queries SQL.
- Clientes HTTP como RestTemplate, WebClient e Feign.
- Propagação do contexto de tracing entre chamadas HTTP.
- Registro de erros e status das operações.

### 5.4 Instrumentação manual

Spans manuais devem ser criados apenas nos pontos de negócio mais relevantes, por exemplo:

- `PedidoService.criarPedido`
- `EstoqueService.reservarEstoque`
- `PagamentoService.autorizar`
- Regras de negócio complexas
- Integrações externas críticas

O objetivo é deixar a trace legível, mostrando claramente as camadas:

```text
Controller → Service → Repository → Banco / Serviço externo
```

### 5.5 Filtro de health check

O `HealthController` (`/api/health`) só retorna 200 e é chamado pelo health check do target group `app-tg` do ALB (via nginx), pelo healthcheck do Docker no `app` (a cada 15 s por réplica) e pelo healthcheck do `nginx`, que faz proxy para o `app`. Com sampling de 100%, cada chamada vira uma trace e polui a busca no Tempo.

O Alloy descarta esses spans antes de enviar ao Tempo (`otelcol.processor.filter`, com a mesma condição OTTL que o OTel Collector usaria). O mesmo receiver OTLP recebe as métricas, que seguem para o Mimir (seção 17.1):

```alloy
otelcol.receiver.otlp "default" {
  http {
    endpoint = "0.0.0.0:4318"
  }
  output {
    traces  = [otelcol.processor.filter.healthcheck.input]
    metrics = [otelcol.processor.batch.default.input]
  }
}

otelcol.processor.filter "healthcheck" {
  error_mode = "ignore"
  traces {
    span = ["attributes[\"url.path\"] == \"/api/health\""]
  }
  output {
    traces = [otelcol.processor.batch.default.input]
  }
}

otelcol.processor.batch "default" {
  output {
    traces  = [otelcol.exporter.otlphttp.tempo.input]
    metrics = [otelcol.exporter.prometheus.mimir.input]
  }
}

otelcol.exporter.otlphttp "tempo" {
  client {
    endpoint = "http://tempo:4318" // rede do Compose
    tls {
      insecure = true
    }
  }
}
```

**Testado localmente em 2026-10-26** (Alloy, com `--stability.level=experimental`, e Mimir 3.2.3):
- Um span com `url.path=/api/health` e outro com `/api/itens`, enviados por OTLP/HTTP: só o segundo foi exportado.
- Um histograma `http.server.request.duration` chegou ao Mimir como `http_server_request_duration_seconds_*`, com `job` vindo do `service.name` e `instance` do `service.instance.id`.
- No teste, o exportador do Tempo foi trocado por um de debug.

### 5.6 Correlação com logs

Os backends devem incluir `trace_id` e `span_id` nos logs estruturados. O OTel Agent coloca os dois no MDC do Logback, e o structured logging do Spring os grava no JSON (seção 4.2). A linha que chega ao Loki fica assim (o Fluent Bit gera JSON compacto, sem espaços):

```json
{"@timestamp":"2026-10-23T13:30:11.482Z","level":"ERROR","logger_name":"...PedidoService","message":"Falha ao reservar estoque","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","span_id":"00f067aa0ba902b7","container_name":"/stockflow_app.2.k3j9x...","env":"production","host":"app-1","origin":"container-logs","service":"app"}
```

No Grafana, a correlação é provisionada por arquivo (`provisioning/datasources/`), com UIDs fixos para que um data source referencie o outro:

```yaml
apiVersion: 1
datasources:
  - name: Loki
    uid: loki
    type: loki
    url: http://loki:3100
    jsonData:
      derivedFields:
        # Log → Trace: o \s* tolera o JSON com ou sem espaço após os dois-pontos
        - name: trace_id
          matcherRegex: '"trace_id":\s*"(\w+)"'
          datasourceUid: tempo
          url: '$${__value.raw}' # $$ escapa a interpolação de variáveis do provisioning

  - name: Tempo
    uid: tempo
    type: tempo
    url: http://tempo:3200
    jsonData:
      # Trace → Logs: monta {service="app", host="app-1"} |= "<trace_id>"
      tracesToLogsV2:
        datasourceUid: loki
        tags:
          - key: service.name
            value: service
          - key: host.name
            value: host
        filterByTraceID: true
        # Logs de spans filhos (manuais) têm outro span_id e sumiriam; ligar só se cada log precisar do span exato
        filterBySpanID: false
        # Folga para relógios e para o horário do driver fluentd
        spanStartTimeShift: -1m
        spanEndTimeShift: 1m
      serviceMap:
        datasourceUid: mimir
```

O `tracesToLogsV2` exige um seletor de stream, e ele só encontra logs porque `service.name` e `host.name` dos spans têm os mesmos valores das labels `service` e `host` (seção 5.2). Por isso o `trace_id` precisa permanecer na linha, e não virar label (seção 4.4).

Com isso, é possível navegar:

```text
Log de erro no Loki (host=app-1 → AZ a; container_name → réplica)
    └── clique no trace_id
        └── Trace no Tempo (service.instance.id=app-1-2, cloud.availability_zone=a)
            └── span com erro ou lentidão
                └── logs daquela trace no container que a atendeu
```

Para ver só os logs de uma réplica: `{service="app", host="app-1"} | json | container_name=~"/stockflow_app\\.2\\..*"`.

**Escopo:** só os logs do `app` gerados dentro de uma requisição (ou de um span manual) têm `trace_id`. RDS, WAF, nginx e RabbitMQ não são instrumentados, e logs de startup ou de jobs fora de um span também ficam sem ele. Para esses, a correlação é por horário (e por `host`, no caso de nginx e RabbitMQ).

---

## 6. Arquitetura na AWS

### 6.1 Componentes AWS

| Componente | Papel |
|---|---|
| EC2 (app) | Hospeda os containers de backend e o Fluent Bit (Docker Swarm, um por AZ) |
| EC2 (observabilidade) | Hospeda Alloy, Loki, Tempo, Mimir e Grafana (Docker Compose) |
| ALB | Distribui tráfego HTTP entre as AZs, encaminha requisições com prefixo `/api` e expõe o Grafana no listener `:3000` |
| RDS | Banco de dados relacional e fonte de logs de banco |
| WAF | Proteção da aplicação e fonte de logs de segurança |
| S3 | Armazenamento dos logs do Loki, das traces do Tempo, das métricas do Mimir e do arquivo bruto de logs |
| CloudWatch Logs | Agregador nativo de logs de RDS e WAF, lido pelo Alloy |
| IAM | Permissões de leitura no CloudWatch Logs e de escrita no S3 para a EC2 de observabilidade (no lab: `LabRole` / `LabInstanceProfile`) |

### 6.2 Componentes open source

| Componente | Papel |
|---|---|
| Fluent Bit | Coleta logs dos containers e envia ao Alloy, com buffer em disco |
| Grafana Alloy | Coletor único: recebe os logs dos containers e os de RDS/WAF e envia ao Loki e ao arquivo bruto no S3; recebe spans e métricas OTLP, filtra e repassa ao Tempo e ao Mimir |
| OpenTelemetry Java Agent | Instrumentação automática dos backends |
| Grafana Loki | Armazenamento e consulta de logs |
| Grafana Tempo | Armazenamento e consulta de traces |
| Grafana Mimir | Armazenamento (S3) e consulta (PromQL) de métricas |
| Grafana | Interface de Live Tail, Trace View, métricas e correlação |
| Grafana Pyroscope | Armazenamento e consulta de profiles (flame graphs), ligados aos spans (seção 18.4) |
| Grafana Faro Web SDK | Logs, erros, Web Vitals e spans do navegador (seção 18.5) |
| k6 | Geração de carga para o cenário de demonstração (roda fora da AWS) |

### 6.3 EC2 de observabilidade

Uma única EC2, em **subnet privada**, roda toda a stack com Docker Compose. Cada componente é um container separado, com deploy, restart e limite de memória próprios.

```text
EC2: observability (Docker Compose)
├── alloy           :3500, :4318, :4040, :9999 e :12347 publicados → loki:3100, tempo:4318, mimir:9009, pyroscope:4040, S3 logs-raw
├── cloudwatch-reader  sem porta publicada → lê CloudWatch Logs, envia a alloy:3501 e alloy:3502
├── loki            :3100 só na rede interna → S3 loki-logs
├── tempo           :3200 só na rede interna → S3 tempo-traces, mimir (metrics-generator)
├── mimir           :9009 só na rede interna → S3 mimir-metrics (TSDB local no EBS)
├── pyroscope       :4040 só na rede interna → S3 pyroscope-profiles (seção 18.4)
└── grafana         :3000 publicado (via ALB) → loki:3100, tempo:3200, mimir:9009, pyroscope:4040
```

**Comunicação:**

- Dentro da EC2, os containers se chamam pelo nome na rede do Compose (`loki:3100`, `tempo:4318`, `tempo:3200`, `mimir:9009`).
- Os backends enviam spans e métricas para o **IP privado fixo** da EC2 (`http://<ip-privado>:4318`), definido no Terraform (`private_ip`) e repassado ao Ansible como variável. O IP privado não muda quando a instância para e volta. O Fluent Bit usa o mesmo IP para enviar logs ao Alloy (`:3500`).
- O Grafana é acessado pelo **`main-alb` existente**, em um listener `:3000` com target group do tipo `instance` apontando para a EC2 (health check em `/api/health`, endpoint nativo do Grafana). O WAF associado ao ALB também protege o Grafana.
- Os spans **não** passam pelo ALB: o ALB é externo, e o tráfego dos backends sairia pelo NAT e voltaria pela internet. A comunicação backend → Alloy é direta, pelo IP privado.
- Não há Cloud Map ou Route 53 envolvidos. O lab bloqueia Cloud Map (ver seção 16), e um endereço fixo dispensa descoberta de serviço.

**Security group:**

| Porta | Origem | Uso |
|---|---|---|
| `3000` | Security group do ALB | Grafana |
| `4318` | Security group das EC2 de app | OTLP HTTP dos backends |
| `3500` | Security group das EC2 de app | Logs do Fluent Bit para o Alloy (API de push do Loki) |
| `4040` | Security group das EC2 de app | Profiles dos backends para o Alloy (seção 18.4) |
| `9999` | Security group das EC2 de app | Métricas do Fluent Bit para o Alloy (seção 18.3) |
| `12347` | Security group do ALB | Faro: dados do navegador via `/collect` (seção 18.5) |
| `12345` | Security group do ALB | Health check do target group do Faro (`/-/ready` do Alloy) |
| `22` | Bastion | Ansible / SSH |

No security group do ALB, a porta `3000` é liberada apenas para os IPs da equipe. Loki, Tempo e Mimir não publicam portas no host: só são acessíveis pela rede interna do Compose, já que não têm autenticação. O Grafana tem login próprio.

**Limitação: Grafana em HTTP.** O listener `:3000` é HTTP, então o login do Grafana trafega sem criptografia. O lab não oferece domínio nem certificado ACM, e a restrição por IP reduz a exposição. Fora do lab, usar um listener HTTPS com certificado. Alternativa sem expor a porta: port forward pelo SSM Session Manager.

**WAF no Grafana:** o WAF do `main-alb` também se aplica ao `:3000`. As regras de rate limit por IP contam as requisições do Grafana (dashboards e Live Tail) junto com qualquer outro tráfego do mesmo IP (ver seção 17.2).

**Credenciais AWS:** os containers usam o `LabInstanceProfile` (`LabRole`) via metadata da instância para CloudWatch Logs e S3. Com IMDSv2, o hop limit precisa ser 2 para que os containers alcancem o metadata.

**Estado do Grafana:** volume Docker no EBS da instância. Dashboards e usuários sobrevivem a restart e reboot. Os data sources Loki, Tempo e Mimir (tipo Prometheus), a correlação por `trace_id` e o dashboard RED são provisionados por arquivo, para recriar o ambiente sem cliques.

### 6.4 Dimensionamento

| Container | Memória (limite inicial) | Observação |
|---|---|---|
| `alloy` | 768 MB | Logs, traces e métricas: recebe, filtra e repassa; sem JVM |
| `cloudwatch-reader` | 256 MB | Lê RDS e WAF; guarda em memória os IDs da janela recente |
| `loki` | 1 GB | Monolítico, volume baixo |
| `tempo` | 1 GB | Monolítico, volume baixo |
| `grafana` | 512 MB | Só consulta Loki, Tempo e Mimir, mas o Grafana 13.3 sofreu OOM com 256 MB ao subir; estabilizou em ~360 MB |
| `mimir` | 1 GB | Monolítico, poucas séries (4 backends); medir sob carga real (no teste local, vazio, usou ~45 MB) |
| `pyroscope` | 768 MB | Monolítico; profiles de 4 backends (seção 18.4) |
| **Total** | **~5,3 GB** | |

Recomendação: **`t3.large`** (2 vCPU, 8 GB), com folga para picos e cache do sistema. Uma `t3.medium` (4 GB) não comporta: a soma dos limites já ocupa toda a memória. O Grafana não pesa: dá para mantê-lo na mesma EC2 sem impacto.

Cada container recebe `mem_limit` no Compose, para que um pico de um (por exemplo, o Loki) não derrube os outros.

### 6.5 Loki e Tempo: containers separados

**Loki e Tempo não devem rodar no mesmo container.** Embora ambos façam parte do ecossistema Grafana, são produtos distintos:

| Aspecto | Grafana Loki | Grafana Tempo |
|---|---|---|
| Tipo de dado | Logs | Traces |
| Origem principal | Fluent Bit e CloudWatch → Alloy | Backends → Alloy (OTLP) |
| Porta padrão | 3100 | 3200 |
| Armazenamento | S3 | S3 |
| Uso principal | Live Tail e busca de logs | Waterfall e investigação de traces |
| Impacto de falha | Live Tail e busca de logs ficam indisponíveis | Trace View e investigação ficam indisponíveis |

Containers separados permitem atualizar, reiniciar e limitar recursos de cada um de forma independente.

Ambos rodam em **modo monolítico**: um único processo com ingestão, consulta e persistência no S3. É a opção mais simples e adequada para o volume de quatro backends. O Tempo monolítico não exige Kafka.

### 6.6 Riscos da EC2 única

- **Ponto único de falha:** se a EC2 cair, logs, traces e métricas param. Os logs dos containers ficam no buffer em disco do Fluent Bit (até `storage.total_limit_size` por nó) e os de RDS/WAF ficam no CloudWatch (3 dias). Os dois chegam quando a EC2 volta. Spans e métricas enviados durante a queda são perdidos.
- **Alloy como coletor único:** um restart do Alloy, por exemplo ao mudar a config, interrompe logs, traces e métricas ao mesmo tempo. Os logs dos containers ficam no buffer do Fluent Bit, e os de RDS/WAF no CloudWatch. Spans e métricas enviados durante o restart podem se perder. Por isso, mudanças de config devem ser recarregadas sem derrubar o processo (`/-/reload`), não com restart do container.
- **WAL e caches** do Loki, do Tempo e do Mimir (TSDB das últimas horas, antes de subir o bloco ao S3) ficam no EBS, então sobrevivem a restart e reboot.
- **Sessão do lab:** ao fim da sessão, as EC2 são paradas. Ao reiniciar, os containers sobem com `restart: unless-stopped`, o Fluent Bit reenvia o que ficou no buffer em disco e o `cloudwatch-reader` retoma a leitura de onde parou, com o horário original de cada evento (seções 4.2 a 4.4).

### 6.7 Evolução futura

Se o volume crescer, os caminhos naturais são:

- Aumentar a instância (`t3.xlarge` ou maior; fora do lab, que limita a `t3.large`).
- Separar Loki e Tempo em EC2s próprias, ou migrar para ECS com descoberta de serviço (fora do lab, Cloud Map/Service Connect).
- Evoluir o Loki para o modo *simple scalable* (write, read e backend separados).
- Aumentar a retenção de métricas do Mimir (meses custam pouco no S3) e rodar o Mimir em mais de uma réplica, ou na arquitetura de *ingest storage* (com Kafka), se for preciso alta disponibilidade.

---

## 7. Separação por origem

Todas as origens chegam ao mesmo Alloy e ao mesmo Loki. A separação lógica é feita pela label `origin`, que também dá nome ao prefixo do arquivo bruto no S3:

| Origem | Identificação |
|---|---|
| Containers | `origin="container-logs"` |
| RDS | `origin="rds-logs"` |
| WAF | `origin="waf-logs"` |

**Volume:** o pico estimado do teste de carga (seção 17.2, ato 3) é de ~300 registros/s e ~200 KB/s. Com `flush 1`, cada um dos dois Fluent Bit envia ~1 s de logs por requisição, o que fica bem abaixo do que um Alloy e um Loki monolíticos aguentam.

**Por que não há barramento:** a versão anterior usava um Kinesis Data Stream (`logs-central`) consumido por um Logstash. Ele foi removido porque a EC2 de observabilidade é única: o buffer em disco do Fluent Bit e a retenção do CloudWatch cobrem as paradas, e os 2 shards custariam ~$21,60/mês mesmo com o lab parado. Se surgirem vários consumidores independentes, ou for preciso fazer replay, um barramento volta a fazer sentido (seção 16).

---

## 8. O que precisa ser programado

O esforço de desenvolvimento é concentrado na instrumentação e no processamento dos logs. A maior parte da plataforma é configuração e deploy de componentes já existentes.

### 8.1 Nos backends REST

| Atividade | Nível de esforço |
|---|---|
| Adicionar o OpenTelemetry Java Agent à imagem | Baixo |
| Configurar variáveis do OTel nos containers do EC2 | Baixo |
| Criar spans manuais em services e repositories críticos | Médio, incremental |
| Logs em JSON com `trace_id` e `span_id` (`logging.structured.format.console=logstash`) | Baixo |
| Adicionar atributos de negócio aos spans | Médio, opcional |

Não é necessário programar a geração de spans para endpoints REST, JDBC, queries e chamadas HTTP externas: o agente OpenTelemetry já cobre esses casos automaticamente.

### 8.2 No processamento de logs (Fluent Bit e Alloy)

Sem código de aplicação. O trabalho é de configuração:

- Fluent Bit: output `loki` e buffer em disco (feito e testado localmente, seção 4.2).
- Alloy (imagem oficial, `--stability.level=experimental`):
  - `loki.source.api` com `use_incoming_timestamp`.
  - Um `loki.source.api` por origem para o `cloudwatch-reader` (seção 4.3).
  - `loki.write` com retentativa sem limite.
  - `otelcol.exporter.awss3` para o arquivo bruto (seções 4.3 e 4.4).
- Validar no lab: a retomada e o timestamp do `cloudwatch-reader` depois de parar a EC2, e o formato do arquivo bruto no Athena.

### 8.3 No Alloy (OTLP), Tempo e Mimir

Não há desenvolvimento de aplicação. O trabalho é de configuração:

- Configurar o receiver OTLP no Alloy (`otelcol.receiver.otlp`, `:4318`).
- Configurar exporters para o Tempo (traces) e para o Mimir (métricas, remote write).
- Configurar o filtro de health check (seção 5.5).
- Configurar armazenamento S3 e metrics-generator no Tempo (seção 17.1).
- Configurar o Mimir monolítico: S3 com prefixos por componente, ring em memória, replication factor 1 e retenção (seção 17.1).
- Configurar retenção (Tempo e Loki, seção 4.4) e limites de ingestão.

### 8.4 No Grafana

Configuração apenas:

- Container `grafana` na EC2 de observabilidade, com estado em volume no EBS.
- Data source Loki.
- Data source Tempo, com service map apontando para o Mimir.
- Data source do tipo Prometheus apontando para o Mimir (`http://mimir:9009/prometheus`).
- Correlação Tempo → Loki.
- Derived field no Loki para extrair `trace_id`.
- Dashboard RED (seção 17.1).
- Views de Live Tail, Trace View e Service Graph.

---

## 9. O que já está pronto

| Capacidade | Já pronto por |
|---|---|
| Instrumentação automática de REST, JDBC e HTTP clients | OpenTelemetry Java Agent |
| Recebimento OTLP | Grafana Alloy (`otelcol.receiver.otlp`) |
| Armazenamento e consulta de traces | Grafana Tempo |
| Armazenamento de logs em objeto | Grafana Loki + S3 |
| Live Tail de logs | Grafana + Loki |
| Waterfall de traces | Grafana + Tempo |
| Correlação log ↔ trace | Grafana Tempo + Loki |
| Métricas de JVM, HTTP e pool de conexões | OpenTelemetry Java Agent |
| Métricas RED e service graph | Tempo metrics-generator + Mimir |
| Buffer em disco e reenvio dos logs dos containers | Fluent Bit (`storage.type filesystem`) |
| Leitura de RDS/WAF no CloudWatch | `cloudwatch-reader` (Python e boto3) |
| Arquivo bruto de logs consultável pelo Athena | Grafana Alloy (`otelcol.exporter.awss3`) |

---

## 10. Fluxo completo

```text
1. Usuário chama a API pelo ALB.

2. O ALB encaminha a requisição ao nginx de uma das AZs, que repassa a um dos quatro backends.

3. O backend:
   - Gera logs estruturados com trace_id.
   - Gera spans e métricas OpenTelemetry.
   - Envia logs ao Fluent Bit.
   - Envia spans e métricas ao Alloy.

4. Fluent Bit envia os logs ao Alloy (HTTP, API de push do Loki), com buffer em disco. RDS e WAF ficam no CloudWatch Logs.

5. O Alloy descarta os spans de health check, envia os spans ao Tempo e as métricas ao Mimir.

6. Tempo persiste as traces no S3 e grava as métricas RED e do service graph no Mimir, que guarda os blocos no S3.

7. O `cloudwatch-reader` lê RDS e WAF no CloudWatch a cada 15 s. O Alloy (EC2 de observabilidade) recebe esses logs e os dos containers, define labels e timestamp e envia ao Loki e ao arquivo bruto no S3.

8. Loki persiste os logs no S3, com retenção de 7 dias.

9. No Grafana:
   - Live Tail mostra os logs em tempo real.
   - Trace View mostra o waterfall da requisição.
   - Dashboard RED e Service Graph mostram taxa, erros e latência.
   - O trace_id permite navegar entre log e trace.
```

---

## 11. Exemplo de investigação

1. No Live Tail do Loki, aparece:

```json
{"level":"ERROR","logger_name":"...PedidoService","message":"Falha ao reservar estoque","trace_id":"4bf92f3577b34da6a3ce929d0e0e4736","host":"app-1","container_name":"/stockflow_app.2.k3j9x...",...}
```

   Já se sabe que foi a réplica 2 do `app-1`, na AZ a.

2. O desenvolvedor clica no botão do `trace_id`, criado pelo derived field.

3. O Grafana abre a trace no Tempo.

4. A trace mostra:

```text
GET /api/pedidos/123
└── PedidoController
    └── PedidoService
        └── EstoqueService.reservarEstoque  ← span lento ou com erro
```

5. A partir do span, o desenvolvedor abre os logs daquela trace no Loki, filtrados pelo `host` do span.

6. Fica claro se o problema está na aplicação, no banco, em uma chamada externa ou em outro serviço.

---

## 12. Logs do ALB

Nesta primeira versão, **os access logs do ALB não serão coletados**.

O ALB atual possui apenas:

- Listener `:80` com o frontend (`web-tg`) como destino padrão e uma regra para `/api` e `/api/*` (`app-tg`, via nginx).
- Listener `:3000` para o Grafana (adicionado por esta proposta).
- Balanceamento de carga entre duas Availability Zones.

Como o roteamento é simples, sem autenticação no ALB nem redirecionamentos, o access log agregaria pouco valor imediato. Além disso, os logs e traces dos backends já mostram endpoint, status, latência, erros, queries e chamadas externas.

Caso seja necessário no futuro — por exemplo, para investigar 5xx percebidos pelo cliente, padrões de tráfego, abuso ou incidentes de segurança — o access log do ALB pode ser habilitado para S3 e integrado posteriormente ao pipeline, sem alterar a arquitetura de logs e traces já existente.

---

## 13. Boas práticas iniciais

- Usar logs estruturados em JSON desde o início.
- Incluir sempre `env`, `service`, `host`, `trace_id` e `span_id` nos logs.
- Usar labels de baixa cardinalidade no Loki (`env`, `origin`, `service`, `host`); `trace_id` e demais campos ficam na linha.
- Usar o horário original do evento como timestamp, nunca o horário de leitura.
- Configurar retenção no Loki, no Tempo e no bucket de arquivo bruto desde o início.
- Usar buffer em disco no Fluent Bit (`storage.type filesystem`) com `retry_limit no_limits`.
- Rodar a stack de observabilidade em uma EC2 `t3.large` com Docker Compose.
- Manter Alloy, Loki, Tempo, Mimir e Grafana em containers separados, com `mem_limit`.
- Não publicar as portas do Loki, do Tempo e do Mimir no host. O Fluent Bit fala com o Alloy, nunca direto com o Loki.
- Fixar a versão da imagem do Alloy, porque o `awss3` é experimental.
- Monitorar o uso do buffer do Fluent Bit nos nós app e os descartes do Alloy (`loki_write_dropped_bytes_total`).
- Usar sampling de 100% nas traces (`OTEL_TRACES_SAMPLER=always_on`, padrão do agente): todo `trace_id` presente nos logs tem a trace correspondente no Tempo, e o link log → trace nunca cai em "trace not found".
- Se o volume crescer, usar tail sampling no Alloy (100% de erros e lentas, amostra das demais) em vez de reduzir o sampling no agente.
- Criar spans manuais somente nos fluxos realmente importantes.
- Não enviar traces pelo pipeline de logs: traces devem seguir pelo pipeline OTLP → Alloy → Tempo.

---

## 14. Roadmap sugerido

### Fase 1 — Logs centralizados

- Recriar no repo infra os log groups do RDS e do WAF, o export de logs do RDS (parameter group de slow query) e o logging do WAF. A PoC foi destruída, e hoje o repo não tem nenhum deles (código na seção 16).
- Criar a EC2 de observabilidade (subnet privada, IP privado fixo, security group com `3500` para as EC2 de app) e instalar Docker Compose via Ansible.
- Deploy do Fluent Bit com output `loki` e buffer em disco (já feito no repo DevOps; exige `otel_endpoint_ip`).
- Adicionar listener `:3000` e target group do Grafana no `main-alb`.
- Subir Alloy (containers e RDS/WAF → Loki e arquivo bruto no S3), Loki e Grafana no Compose.
- Validar a retomada do `cloudwatch-reader` depois de parar a EC2.
- Configurar retenção do Loki e lifecycle do bucket `logs-raw`.
- Habilitar Live Tail no Grafana.

### Fase 2 — Tracing

- Adicionar OTel Java Agent aos backends.
- Subir o Tempo (com S3) no Compose e o pipeline OTLP no Alloy.
- Apontar os backends para `http://<ip-privado>:4318`.
- Configurar data source Tempo no Grafana.
- Incluir `trace_id` nos logs.
- Configurar correlação Tempo ↔ Loki.

### Fase 3 — Complementos

- Métricas: pipeline de métricas no Alloy, Mimir e metrics-generator do Tempo (seção 17.1).
- Cenário de demonstração com k6 (seção 17.2).
- Exemplars, `trace_id` no slow query do RDS e self-monitoring com alertas (seções 18.1 a 18.3).
- Pyroscope com span profiles e Faro no frontend (seções 18.4 e 18.5).
- Apps Drilldown: pattern ingester no Loki e TraceQL metrics no Tempo (seção 18.6).

### Fase 4 — Evolução

- Adicionar spans de negócio nos serviços críticos.
- Criar alertas baseados em logs.
- Ajustar retenção e capacidade conforme o volume real; avaliar tail sampling se o volume de traces pesar.
- Avaliar separação do Loki em write/read/backend se o volume justificar.
- Reavaliar a necessidade de access logs do ALB.

### Previsão de tempo

Estimativa para 1 pessoa com experiência em Terraform e AWS.

| Etapa | Horas |
|---|---|
| Log groups do RDS e WAF, export do RDS e logging do WAF (já validados na PoC) | 1 h |
| Fluent Bit: output `loki` e buffer em disco (já feito e testado localmente) | 1 h (deploy) |
| EC2 de observabilidade: Terraform (subnet privada, IP fixo, SG com `3500` e `4318`, listener `:3000` no ALB) + Docker Compose via Ansible | 4 h |
| Alloy: Fluent Bit → Loki (`loki.source.api`, timestamp, labels, retentativas) e arquivo bruto no S3 | 4 h |
| Leitor próprio de RDS/WAF no CloudWatch (validar a retomada após parada da EC2) | 3 h |
| Loki + S3 + retenção | 4 h |
| Grafana + provisioning dos data sources | 3 h |
| **Fase 1: logs + Live Tail** | **20 h** |
| OTel Java Agent nos 4 backends (mesma imagem: jar + `JAVA_TOOL_OPTIONS`) | 4 h |
| Structured logging no backend (`logging.structured.format.console=logstash`) com `trace_id`/`span_id` | 2 h |
| Alloy (OTLP, filtro de health check) + Tempo + S3 | 4 h |
| Correlação Loki ↔ Tempo no Grafana | 2 h |
| **Fase 2: tracing** | **12 h** |
| Métricas: Alloy + Mimir (S3, ring, retenção) + metrics-generator + dashboard RED | 6 h |
| Cenário de demonstração (script k6 + roteiro) | 2 h |
| Exemplars: Mimir, Tempo e data source (seção 18.1) | 2 h |
| sqlcommenter + derived field do RDS, validado no lab (seção 18.2) | 3 h |
| Self-monitoring: scrape, Fluent Bit push, alertas e dashboard (seção 18.3) | 3 h |
| Pyroscope: extensão no backend, Alloy, S3 e `tracesToProfiles` (seção 18.4) | 5 h |
| Faro: SDK no frontend, regra no ALB, receiver no Alloy (seção 18.5) | 6 h |
| Drilldown: pattern ingester no Loki, `local-blocks` no Tempo (seção 18.6) | 1 h |
| **Fase 3: complementos** | **28 h** |
| **Subtotal** | **60 h** |
| Folga de ~20% para bloqueios do Learner Lab | 12 h |
| **Total** | **~72 h (cerca de 9 dias úteis)** |
| Fase 4: evolução | Contínua |

Riscos: bloqueios do Learner Lab (reservar ~20% de folga), o componente experimental `awss3` do Alloy e compatibilidade do OTel Java Agent com Spring Boot 4 / Spring Framework 7 (usar a versão mais recente do agente).

---

## 15. Organização dos repositórios

Separar a observabilidade em um repositório próprio:

- **Repo infra (`DevOps` atual):** VPC, RDS (export de logs), WAF (logging), os CloudWatch Log Groups, o `main-alb` e, no Ansible das EC2 de app, o Fluent Bit e as variáveis do OTel Agent. Os log groups, o export do RDS e o logging do WAF ainda precisam ser recriados (seção 14).
- **Repo observabilidade (Terraform e Ansible):** buckets S3, a EC2 de observabilidade com seu security group, o listener `:3000` e o target group do Grafana no `main-alb`, e o Compose com Alloy, Loki, Tempo, Mimir e Grafana.

O repo de observabilidade localiza os recursos do repo infra por **data source por nome** (`data "aws_cloudwatch_log_group"`, `data "aws_lb"`, `data "aws_subnet"`), sem `terraform_remote_state`. O contrato entre os repos são valores combinados previamente:

| Valor | Definido em | Usado em |
|---|---|---|
| Nomes dos log groups, do ALB e das subnets | Repo infra | Repo observabilidade (data sources) |
| IP privado fixo da EC2 de observabilidade | Repo observabilidade (`private_ip`) | Repo infra (`otel_endpoint_ip`, OTel Agent e Fluent Bit) |

Como os valores são combinados de antemão, não há dependência circular: a ordem de apply é infra → observabilidade. Até a observabilidade subir, o Fluent Bit e o OTel Agent apenas falham ao enviar. O Fluent Bit, com `retry_limit no_limits` e buffer em disco (seção 4.2), guarda os logs e reenvia quando o Alloy existir. O OTel Agent descarta spans e métricas que não conseguir entregar.

---

## 16. Notas da prova de conceito e dos testes no lab

**Histórico:** esta PoC validou a versão anterior da arquitetura, com Kinesis e Logstash, que foi substituída pelo Fluent Bit enviando direto ao Alloy (seções 3 e 7). Os pontos sobre `LabRole`, log groups, slow query no RDS e tipos de instância continuam valendo. Os de Kinesis, DynamoDB e Firehose ficam como registro do que foi testado e descartado.

Implementado e testado em 2026-10-24 no repo `DevOps/prod/terraform`, depois destruído. O fluxo WAF → CloudWatch → Subscription Filter → Kinesis funcionou: os logs chegaram na stream. Os logs do RDS não chegaram a ser vistos porque não houve erro nem query lenta durante o teste.

Pontos importantes:

- **LabRole:** o Learner Lab não permite criar roles. A `LabRole` (via `data "aws_iam_role"`) funcionou como `role_arn` dos subscription filters.
- **Kinesis no lab:** o provider AWS (todas as versões, v4 até a main) sempre chama `IncreaseStreamRetentionPeriod` ao criar a stream, e o lab bloqueia essa chamada. A stream é criada, mas fica tainted. Opções: `terraform untaint aws_kinesis_stream.logs_central` e aplicar de novo, ou criar a stream pelo console e trazer para o Terraform com um bloco `import`.
- **Slow query no RDS:** precisa dos parâmetros `slow_query_log=1`, `long_query_time=1` e `log_output=FILE` no parameter group, além de `enabled_cloudwatch_logs_exports = ["error", "slowquery"]` na instância.
- **Log groups:** criar no Terraform antes do RDS (`depends_on`), senão o RDS cria sozinho e é preciso usar `terraform import`.
- **Formato no Kinesis:** cada registro do CloudWatch vem compactado em gzip (a API exibe em base64), com um JSON `{messageType, logGroup, logEvents[]}`. Ignorar `CONTROL_MESSAGE`. O consumidor deriva `origin` do `logGroup`.
- **DynamoDB no lab (testado em 2026-10-24):** criação de tabela provisionada, `PutItem`, `UpdateItem`, `Scan` e `DeleteTable` funcionaram com o usuário `voclabs`. O IAM policy simulator confirmou que a `LabRole` permite as ações de DynamoDB, Kinesis (`GetRecords`, `GetShardIterator`, `ListShards`, `DescribeStream`) e `cloudwatch:PutMetricData` usadas pela KCL.
- **Teste completo de permissões (2026-10-24):** recursos `permtest-*` criados, testados e apagados.
  - Provisionamento (`voclabs`): S3, Kinesis, CloudWatch Logs + Subscription Filter com `LabRole`, Secrets Manager, SSM, security groups, ECS cluster com `FARGATE` e `FARGATE_SPOT`, task definition com `LabRole` (task e execution), ALB interno + target group `ip` + listener e hosted zone privada no Route 53: **OK**.
  - Runtime (mesma `LabRole` que a EC2 de observabilidade usa via `LabInstanceProfile`): task em Fargate Spot executou `kinesis:PutRecord`/`ListShards`/`GetShardIterator`/`GetRecords`, criação e escrita em tabela DynamoDB, `s3` put/list/delete, `cloudwatch:PutMetricData` e leitura de secret do Secrets Manager: **OK**.
  - Negados: `kinesis:IncreaseStreamRetentionPeriod` (SCP do lab, já conhecido; a stream fica com 24h) e `servicediscovery:CreatePrivateDnsNamespace` (sem Service Connect/Cloud Map). Por isso a stack saiu do ECS e foi para uma EC2 com Docker Compose (seção 6.3).
  - ECS, ALB interno e Route 53 foram testados apenas como alternativas e **não fazem parte da arquitetura final**: a comunicação entre os componentes de observabilidade é pela rede Docker dentro da EC2.
  - A primeira criação de cluster ECS com capacity providers falha com "Unable to assume the service linked role" enquanto a `AWSServiceRoleForECS` propaga. Repetir após alguns segundos resolve.
- **Firehose como segundo consumidor (testado em 2026-10-25, descartado):** Firehose com origem no Kinesis e processador `Decompression` descompacta corretamente os registros do CloudWatch, mas rejeita o JSON puro do Fluent Bit (`payload is not compressed using GZIP format`). O `compression gzip` no output `kinesis_streams` só existe em versões novas do Fluent Bit (presente na 5.1, ausente na 3.2), e mesmo com ele o Firehose rejeitou parte dos registros (`input data does not conform to cloudwatch log`): o processador é feito para o formato do CloudWatch. Sem descompressão, os arquivos no S3 misturam gzip e JSON e o Athena não lê. Na época, foi substituído pelo output `s3` do Logstash. Hoje o arquivo bruto é gravado pelo Alloy (seção 4.4).
- **Tipo de instância (testado em 2026-10-25, `run-instances --dry-run` com `LabInstanceProfile`, IMDSv2 com hop limit 2 e EBS gp3 de 30 GB):** `t3.medium` e `t3.large` permitidas; `t3.xlarge` negada (`UnauthorizedOperation`). A cota de vCPU não pôde ser consultada (`servicequotas:GetServiceQuota` negado).
- **Para ver os dados:** pelo console, Kinesis → Data viewer (Trim horizon) mostra os registros, mas compactados; a aba Monitoring → Incoming data confirma a chegada. Pela CLI: `get-shard-iterator` + `get-records`, depois `base64 -d | gunzip`.

Código usado na PoC. Na arquitetura atual, continuam os log groups e o logging do WAF; o stream e os subscription filters saem.

```hcl
data "aws_iam_role" "lab" {
  name = "LabRole"
}

resource "aws_kinesis_stream" "logs_central" {
  name = "logs-central" # retenção padrão de 24h

  stream_mode_details {
    stream_mode = "ON_DEMAND"
  }
}

resource "aws_cloudwatch_log_group" "rds" {
  for_each          = toset(["error", "slowquery"])
  name              = "/aws/rds/instance/app-db/${each.key}"
  retention_in_days = 3
}

resource "aws_cloudwatch_log_group" "waf" {
  name              = "aws-waf-logs-main-alb-waf"
  retention_in_days = 3
}

resource "aws_wafv2_web_acl_logging_configuration" "main" {
  resource_arn            = aws_wafv2_web_acl.main.arn
  log_destination_configs = [aws_cloudwatch_log_group.waf.arn]
}

resource "aws_cloudwatch_log_subscription_filter" "to_kinesis" {
  for_each = merge(
    { for k, g in aws_cloudwatch_log_group.rds : "rds-${k}" => g.name },
    { waf = aws_cloudwatch_log_group.waf.name },
  )

  name            = "${each.key}-to-kinesis"
  log_group_name  = each.value
  filter_pattern  = ""
  destination_arn = aws_kinesis_stream.logs_central.arn
  role_arn        = data.aws_iam_role.lab.arn
  distribution    = "Random"
}
```

---

## 17. Complementos

### 17.1 Métricas: o terceiro pilar

Logs dizem **o que aconteceu**; traces dizem **por onde a requisição passou**; métricas dizem **como o sistema está se comportando ao longo do tempo** (quantas requisições por segundo, quantos erros, quanta memória). Sem métricas, não há como responder "a API ficou mais lenta hoje do que ontem?" sem abrir trace por trace.

São duas fontes de métricas, e nenhuma exige código novo nos backends:

**1. Métricas enviadas pelo OTel Java Agent.** O mesmo agente que gera os spans também exporta métricas por OTLP a cada 60 s (`otel.metrics.exporter=otlp` é o padrão). Exemplos:

| Métrica (nome no formato Prometheus) | O que mostra |
|---|---|
| `http_server_request_duration_seconds` | Histograma de latência por rota (`http_route`) e status |
| `jvm_memory_used_bytes` | Heap e non-heap |
| `jvm_gc_duration_seconds` | Tempo gasto em garbage collection |
| `jvm_thread_count` | Threads ativas |
| `db_client_connections_usage` | Conexões do pool HikariCP em uso |

Elas seguem o mesmo caminho dos spans (backend → Alloy), e o Alloy repassa ao Mimir por **remote write**. Isso evita o modelo tradicional de *scrape*, que exigiria descobrir os 4 containers espalhados por 2 swarms.

**2. Métricas derivadas das traces (metrics-generator do Tempo).** O Tempo calcula métricas a partir dos spans que recebe e grava no Mimir:

- **Span metrics (RED):** taxa (*Rate*), erros (*Errors*) e duração (*Duration*) por endpoint, em `traces_spanmetrics_calls_total` e `traces_spanmetrics_latency_bucket`.
- **Service graph:** um mapa de quem chama quem, com taxa e erro em cada aresta, em `traces_service_graph_request_total`. Bancos e filas não instrumentados aparecem como **nós virtuais** a partir dos atributos dos spans (`db.system`, `messaging.system`), então o grafo mostra `app → mysql` e `app → rabbitmq`. O nginx não é instrumentado e não aparece.

Como o Alloy já descarta os spans de `/api/health` antes do Tempo, as métricas RED já saem sem o ruído do health check. As métricas do agente (`http_server_request_duration_seconds`) incluem o health check; nas consultas, filtrar com `http_route!="/api/health"`.

**Configuração:**

No Alloy, as métricas saem do `otelcol.processor.batch` (seção 5.5), são convertidas ao formato Prometheus e enviadas ao Mimir por remote write:

```alloy
otelcol.exporter.prometheus "mimir" {
  forward_to = [prometheus.remote_write.mimir.receiver]
}

prometheus.remote_write "mimir" {
  endpoint {
    url = "http://mimir:9009/api/v1/push"
  }
}
```

Mimir monolítico (`grafana/mimir:3.2.3`, `-target=all`), na arquitetura clássica, com blocos no S3 e retenção de 15 dias:

```yaml
multitenancy_enabled: false
server:
  http_listen_port: 9009
common:
  storage:
    backend: s3
    s3:
      endpoint: s3.us-east-1.amazonaws.com
      region: us-east-1
      bucket_name: mimir-metrics   # sem chaves: credenciais do LabInstanceProfile
# Blocos, ruler e alertmanager no mesmo bucket exigem prefixos diferentes (o Mimir recusa a config sem eles)
blocks_storage:
  storage_prefix: blocks
  tsdb:
    dir: /data/tsdb                # volume no EBS: blocos das últimas ~2 h antes de subir ao S3
  bucket_store:
    sync_dir: /data/tsdb-sync
ruler_storage:
  storage_prefix: ruler
alertmanager_storage:
  storage_prefix: alertmanager
compactor:
  data_dir: /data/compactor
ingester:
  ring:
    replication_factor: 1
    kvstore:
      store: inmemory
store_gateway:
  sharding_ring:
    replication_factor: 1
limits:
  compactor_blocks_retention_period: 15d
```

Remote write em `http://mimir:9009/api/v1/push` e PromQL em `http://mimir:9009/prometheus`. No Compose: volume em `/data` e `mem_limit: 1g`.

**Testado localmente em 2026-10-26** (Mimir 3.2.3, com um S3 local no lugar do AWS S3):
- O Mimir subiu sem Kafka, na arquitetura clássica.
- Passou na verificação de conexão com o object storage.
- Recebeu remote write de um Alloy e respondeu PromQL em `/prometheus`.

Na AWS, falta conferir que as credenciais do `LabInstanceProfile` são lidas sem chaves no config, a mesma premissa do Loki e do Tempo.

Tempo com o metrics-generator ligado:

```yaml
metrics_generator:
  storage:
    path: /var/tempo/generator/wal
    remote_write:
      - url: http://mimir:9009/api/v1/push
overrides:
  defaults:
    metrics_generator:
      processors: [service-graphs, span-metrics]
```

No Grafana: data source do tipo Prometheus provisionado com a URL `http://mimir:9009/prometheus` e, no data source Tempo, **Service map → Mimir**. A aba **Service Graph** aparece em Explore → Tempo.

**Dashboard RED (consultas PromQL):**

```promql
# Taxa: requisições por segundo, por endpoint
sum by (span_name) (rate(traces_spanmetrics_calls_total{span_kind="SPAN_KIND_SERVER"}[5m]))

# Erros: proporção de spans com erro
sum(rate(traces_spanmetrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m]))
  / sum(rate(traces_spanmetrics_calls_total[5m]))

# Duração: p95 por endpoint
histogram_quantile(0.95, sum by (le, span_name) (rate(traces_spanmetrics_latency_bucket{span_kind="SPAN_KIND_SERVER"}[5m])))
```

Os três pilares se conectam no Grafana: um pico no painel de erros leva à busca de traces com erro no Tempo, e cada trace leva aos logs pelo `trace_id`.

### 17.2 Cenário de demonstração (k6)

O objetivo é mostrar o sistema funcionando ao vivo, e não só o diagrama: gerar tráfego real, provocar falhas controladas e seguir a investigação no Grafana.

**Onde roda:** contra o DNS do `main-alb`, a partir de um **IP diferente do usado para abrir o Grafana** (por exemplo, outro computador ou o hotspot do celular). O Grafana está atrás do mesmo WAF (seção 6.3): se o k6 rodasse do mesmo IP, o bloqueio do ato 3 tiraria o acesso ao Grafana justamente quando o Live Tail deveria mostrar o `BLOCK`, e no ato 1 as requisições do Grafana somariam às do k6 no rate limit. Duas regras do WAF afetam o teste:

- `BlockNonBrazilTraffic`: o k6 precisa rodar de um IP no Brasil.
- `RateLimitPerIpAggressive` (500 req/min por IP) e `RateLimitPerIpModerate` (2000 req em 5 min, ~400/min): o tráfego normal precisa ficar abaixo de **~400 req/min**. Com 4 usuários virtuais e 1 s de pausa, são ~240 req/min.

**Script base** (`demo.js`):

```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE = __ENV.BASE_URL; // http://<dns-do-alb>/api

export const options = { vus: 4, duration: '10m' };

export function setup() {
  const res = http.post(`${BASE}/auth/login`,
    JSON.stringify({ email: __ENV.EMAIL, senha: __ENV.SENHA }),
    { headers: { 'Content-Type': 'application/json' } });
  return { token: res.json('accessToken') };
}

export default function ({ token }) {
  const params = { headers: { Authorization: `Bearer ${token}` } };
  for (const path of ['/dashboard', '/itens', '/clientes', '/encomendas/kpis']) {
    check(http.get(`${BASE}${path}`, params), { 'status 200': (r) => r.status === 200 });
  }
  sleep(1);
}
```

Execução: `k6 run -e BASE_URL=http://<dns-do-alb>/api -e EMAIL=<usuario-demo> -e SENHA=<senha> demo.js`.

**Roteiro em três atos:**

| Ato | Ação | O que mostrar no Grafana |
|---|---|---|
| 1. Normal | Rodar o `demo.js` | Live Tail com os logs chegando; painel RED estável; service graph `app → mysql`; um trace qualquer no waterfall |
| 2. Falha na fila | Com o k6 rodando, parar o RabbitMQ de uma AZ (`docker service scale stockflow_rabbitmq=0` no `app-1`) e chamar `POST /api/auth/esqueci-senha`, que publica na fila | Logs `ERROR` no Live Tail → clique no `trace_id` → span de publish no RabbitMQ com erro ou lento; aresta `app → rabbitmq` com erro no service graph; taxa de erro subindo no RED. Depois, `docker service scale stockflow_rabbitmq=1` |
| 3. Ataque bloqueado | Ultrapassar o limite do WAF de propósito (`k6 run --vus 30 --duration 1m`) | Respostas 429 no k6 e, até ~45 s depois (seção 4.5), `{origin="waf-logs"} \|= "BLOCK"` no Live Tail, mostrando o pipeline WAF → CloudWatch → leitor → Alloy → Loki |

O ato 3 vem por último, porque o IP do k6 fica bloqueado por alguns minutos depois de estourar o limite. No ato 2, validar antes da apresentação como o endpoint responde com a fila parada: a publicação acontece após o commit (`afterCommit`), então o erro pode aparecer no span e nos logs sem mudar o status HTTP.

O usuário da demonstração deve ser uma conta de teste, nunca credenciais reais no script.


---

## 18. Extensões

Seis adições sobre a stack das seções 3 a 17. Cada uma fecha uma lacuna que a proposta já admite ou estende a investigação para onde ela ainda não chega:

| # | Extensão | Lacuna que fecha |
|---|---|---|
| 18.1 | Exemplars | Do painel de métricas até a trace, hoje só por busca no Tempo |
| 18.2 | `trace_id` no slow query do RDS | RDS correlacionado só por horário (seção 5.6) |
| 18.3 | Self-monitoring | Buffer do Fluent Bit e descartes do Alloy sem coleta (seção 13) |
| 18.4 | Profiling contínuo (Pyroscope) | A trace mostra qual span demorou, mas não qual código dentro dele |
| 18.5 | Observabilidade do frontend (Faro) | A trace começa no backend; o navegador fica de fora |
| 18.6 | Drilldown | Explorar os dados exige saber LogQL, PromQL e TraceQL |

Com elas, o Grafana passa a navegar entre os quatro sinais: **métrica → trace → log → profile**, e a trace passa a ir do navegador ao banco.

### 18.1 Exemplars: da métrica direto para a trace

Um *exemplar* é um `trace_id` anexado a um ponto de um histograma. No painel de latência, cada ponto de exemplar vira um link para uma trace real com aquela latência: o p95 subiu, um clique no ponto e a trace lenta abre no Tempo.

São duas fontes, as mesmas da seção 17.1:

- **OTel Java Agent:** já anexa exemplars aos histogramas por padrão (`otel.metrics.exemplar.filter=trace_based`). Como o sampling é de 100%, toda medição dentro de uma requisição tem um exemplar. O `otelcol.exporter.prometheus` e o `prometheus.remote_write` do Alloy repassam ao Mimir.
- **metrics-generator do Tempo:** precisa de `send_exemplars: true`, que é `false` por padrão.

O Mimir **descarta exemplars por padrão** (`max_global_exemplars_per_user: 0`):

```yaml
# mimir.yaml (somar ao bloco limits da seção 17.1)
limits:
  compactor_blocks_retention_period: 15d
  max_global_exemplars_per_user: 100000
```

```yaml
# tempo.yaml (seção 17.1)
metrics_generator:
  storage:
    remote_write:
      - url: http://mimir:9009/api/v1/push
        send_exemplars: true
```

```alloy
prometheus.remote_write "mimir" {
  endpoint {
    url            = "http://mimir:9009/api/v1/push"
    send_exemplars = true // padrão, explícito para documentar
  }
}
```

No data source do Mimir (provisioning da seção 5.6), as duas fontes usam nomes de label diferentes para o mesmo `trace_id`:

```yaml
  - name: Mimir
    uid: mimir
    type: prometheus
    url: http://mimir:9009/prometheus
    jsonData:
      exemplarTraceIdDestinations:
        - name: trace_id   # exemplars do OTel Agent
          datasourceUid: tempo
        - name: traceID    # exemplars do metrics-generator do Tempo
          datasourceUid: tempo
```

Nos painéis de latência do dashboard RED, ligar a opção **Exemplars** na query.

**Na demonstração (ato 2):** no painel de p95, clicar no exemplar do pico e cair direto na trace com o erro do RabbitMQ, sem buscar no Tempo.

### 18.2 `trace_id` no slow query do RDS (sqlcommenter)

Hoje uma query no slow query log do RDS não diz de qual requisição veio (seção 5.6). O OTel Java Agent pode anexar o contexto da trace a cada SQL, no formato [sqlcommenter](https://google.github.io/sqlcommenter/):

```sql
SELECT * FROM pedidos WHERE id = ? /*traceparent='00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01'*/
```

O MySQL grava o texto recebido no slow query log, comentário incluído. A linha chega ao Loki pelo caminho já existente (CloudWatch → leitor → Alloy, seção 4.3), e um derived field transforma o `traceparent` em link para o Tempo.

No `docker-compose.yml.j2` do backend (seção 5.2):

```yaml
environment:
  OTEL_INSTRUMENTATION_JDBC_EXPERIMENTAL_SQLCOMMENTER_ENABLED: "true"
```

No data source Loki (seção 5.6), um segundo derived field:

```yaml
      derivedFields:
        # ... trace_id (seção 5.6)
        - name: trace_id_sql
          matcherRegex: "traceparent='00-(\\w{32})-"
          datasourceUid: tempo
          url: '$${__value.raw}'
```

Com isso, o caminho fica: query lenta no `{origin="rds-logs"}` → clique → trace que a disparou → logs do backend daquela requisição.

**Cuidados:**

- **Experimental**, desligado por padrão no agente. Fixar a versão do agente e validar o formato do comentário.
- Cada SQL passa a ter um texto único. A documentação do agente alerta que isso pode afetar o desempenho do banco, porque caches de statement no servidor deixam de reaproveitar. O MySQL Connector/J usa prepared statements no cliente por padrão (`useServerPrepStmts=false`), então o impacto esperado é pequeno, mas precisa ser medido sob carga.
- Só aparecem queries acima de `long_query_time` (1 s, seção 16). Na demonstração, baixar temporariamente para `0.2` no parameter group, ou provocar uma query lenta conhecida.
- Validar no lab que o comentário chega ao slow query log do RDS (alguns proxies e clientes removem comentários; o JDBC não remove).

### 18.3 Self-monitoring: quem vigia o pipeline

A seção 13 recomenda monitorar o buffer do Fluent Bit e os descartes do Alloy, mas nada coleta essas métricas. Sem isso, o pipeline pode parar em silêncio, e o Live Tail vazio parece "nenhum erro".

**Na EC2 de observabilidade:** o Alloy raspa a si mesmo, os outros componentes (todos expõem `/metrics` na rede do Compose) e o host, e manda tudo ao Mimir pelo `prometheus.remote_write` que já existe:

```alloy
prometheus.exporter.self "alloy" {}

prometheus.exporter.unix "host" {
  procfs_path = "/host/proc" // volumes /proc, /sys e / do host montados read-only no container
  sysfs_path  = "/host/sys"
  rootfs_path = "/host/root"
}

prometheus.scrape "stack" {
  targets = array.concat(
    prometheus.exporter.self.alloy.targets,
    prometheus.exporter.unix.host.targets,
    [
      {"__address__" = "loki:3100", "job" = "loki"},
      {"__address__" = "tempo:3200", "job" = "tempo"},
      {"__address__" = "mimir:9009", "job" = "mimir"},
      {"__address__" = "grafana:3000", "job" = "grafana"},
    ],
  )
  forward_to = [prometheus.remote_write.mimir.receiver]
}
```

**Nos nós app (Fluent Bit):** em vez de o Alloy raspar os nós app (IPs que mudam, porta a mais em cada nó), o Fluent Bit **envia** as próprias métricas, no mesmo modelo push do resto da proposta:

```ini
[INPUT]
    name            fluentbit_metrics
    tag             internal_metrics
    scrape_interval 15

[OUTPUT]
    name   prometheus_remote_write
    match  internal_metrics
    host   {{ otel_endpoint_ip }}
    port   9999
    uri    /api/v1/metrics/write
    add_label host {{ inventory_hostname }}
```

O `match *` do output `loki` (seção 4.2) também casaria a tag `internal_metrics`, mas o `fluentbit_metrics` gera métricas, não logs, e o output `loki` as ignora.

```alloy
prometheus.receive_http "fluentbit" {
  http {
    listen_address = "0.0.0.0"
    listen_port    = 9999
  }
  forward_to = [prometheus.remote_write.mimir.receiver]
}
```

Liberar a porta `9999` no security group para as EC2 de app (seção 6.3).

**Alertas** (Grafana Alerting, provisionado por arquivo em `provisioning/alerting/`, contact point por webhook do Discord ou Telegram, sem SNS):

| Alerta | Consulta | Significado |
|---|---|---|
| Pipeline de logs parado | `absent_over_time({service="app", host="app-1"}[5m])` (LogQL; um por host) | Nenhum log do `app-1` em 5 min |
| Alloy não entrega ao Loki | `rate(fluentbit_output_retries_total[5m]) > 0` por 5 min | Fluent Bit acumulando no buffer em disco |
| Descarte no Alloy | `increase(loki_write_dropped_bytes_total[5m]) > 0` | Logs perdidos entre Alloy e Loki |
| Disco da EC2 | `node_filesystem_avail_bytes{mountpoint="/host/root"} / node_filesystem_size_bytes < 0.15` | WAL e TSDB podem encher o EBS |
| Memória perto do limite | `process_resident_memory_bytes{job=~"loki|tempo|mimir"}` acima de 85% do `mem_limit` do container | Um componente perto do OOM |

Conferir os nomes das métricas do `fluentbit_metrics` na versão 3.2 antes de criar os alertas.

Os alertas disparam quando o lab é parado. Silenciar ou aceitar o disparo ao fim de cada sessão.

**Dashboard "Saúde da observabilidade":** taxa de ingestão do Loki, Tempo e Mimir, retries e chunks em buffer do Fluent Bit por host, memória e disco da EC2.

### 18.4 Profiling contínuo com Pyroscope: o quarto pilar

A trace mostra que `EstoqueService.reservarEstoque` levou 120 ms; não mostra **qual método** gastou o tempo. O profiling contínuo amostra a pilha da JVM o tempo todo e gera flame graphs. Com **span profiles**, cada span ganha um botão **Profiles** no Tempo que abre o flame graph daquele trecho da requisição, até a linha de código.

```text
Profiles:   Backends (extensão pyroscope-otel) ──> Alloy :4040 ──> Pyroscope ──> S3
```

**No backend:** a extensão `pyroscope-otel-javaagent-extension.jar` roda dentro do mesmo OTel Java Agent da seção 5.2. Ela inicia o profiler (async-profiler) e marca as amostras com o `span_id`. Sem código novo, só mais um jar na imagem e variáveis no `docker-compose.yml.j2`:

```yaml
environment:
  OTEL_JAVAAGENT_EXTENSIONS: /otel/pyroscope-otel-javaagent-extension.jar
  OTEL_PYROSCOPE_START_PROFILING: "true"
  OTEL_PYROSCOPE_ADD_PROFILE_URL: "false"
  OTEL_PYROSCOPE_ADD_PROFILE_BASELINE_URL: "false"
  PYROSCOPE_APPLICATION_NAME: app # igual ao service.name
  PYROSCOPE_SERVER_ADDRESS: "http://{{ otel_endpoint_ip }}:4040" # Alloy, não o Pyroscope
  PYROSCOPE_LABELS: "host={{ inventory_hostname }}"
  PYROSCOPE_FORMAT: jfr
  PYROSCOPE_PROFILER_EVENT: itimer # CPU, sem privilégio de perf_event no container
  PYROSCOPE_PROFILER_ALLOC: 512k
  PYROSCOPE_PROFILER_LOCK: 10ms
  PYROSCOPE_UPLOAD_INTERVAL: 15s
```

**No Alloy:** o mesmo papel dos outros sinais. O Pyroscope não tem autenticação e fica só na rede do Compose; os backends falam com o Alloy:

```alloy
pyroscope.receive_http "backends" {
  http {
    listen_address = "0.0.0.0"
    listen_port    = 4040
  }
  forward_to = [pyroscope.write.default.receiver]
}

pyroscope.write "default" {
  endpoint {
    url = "http://pyroscope:4040"
  }
}
```

**Pyroscope** (`grafana/pyroscope`, monolítico, versão fixada), com blocos no S3 e credenciais do `LabInstanceProfile`:

```yaml
storage:
  backend: s3
  s3:
    endpoint: s3.us-east-1.amazonaws.com
    region: us-east-1
    bucket_name: pyroscope-profiles
    native_aws_auth_enabled: true # cadeia de credenciais do SDK (metadata da instância), sem chaves
```

Retenção de 7 dias: conferir a opção na versão fixada (na v1, `limits.compactor_blocks_retention_period: 7d`). Volume em `/data` e `mem_limit: 768m` no Compose.

**No Grafana:**

```yaml
  - name: Pyroscope
    uid: pyroscope
    type: grafana-pyroscope-datasource
    url: http://pyroscope:4040

  # no data source Tempo (seção 5.6), somar:
      tracesToProfiles:
        datasourceUid: pyroscope
        profileTypeId: process_cpu:cpu:nanoseconds:cpu:nanoseconds
        tags:
          - key: service.name
            value: service_name
```

**Cuidados:**

- Spans mais curtos que o intervalo de amostragem (10 ms) podem não ter amostras. Os spans lentos, que são os que interessam, têm.
- O overhead do async-profiler costuma ficar em poucos por cento de CPU. Medir com o k6 antes e depois.
- Testar a extensão com Spring Boot 4 e a versão do OTel Agent usada (mesmo risco da seção 14).
- Liberar a porta `4040` no security group para as EC2 de app.

**Na demonstração (ato 1):** em uma trace qualquer, abrir **Profiles** no span do controller e mostrar o flame graph: Jackson serializando, Hibernate montando entidades e o tempo esperando o JDBC.

### 18.5 Observabilidade do frontend com Grafana Faro

O frontend (`web-tg`, seção 12) não é instrumentado: a trace começa no backend, e erros de JavaScript e lentidão percebida pelo usuário ficam invisíveis. O **Faro Web SDK** roda no navegador e envia ao Alloy logs, exceptions, Web Vitals (LCP, INP, CLS) e spans. A instrumentação de `fetch` injeta o `traceparent` nas chamadas à API, então **a trace passa a começar no clique do usuário** e segue até o RDS.

```text
Frontend:   Navegador ──> ALB :80 /collect ──> Alloy :12347 ──┬──> Loki  (logs, exceptions, Web Vitals)
                                                              └──> Tempo (spans do navegador)
```

**No frontend:**

```javascript
import { initializeFaro, getWebInstrumentations } from '@grafana/faro-web-sdk';
import { TracingInstrumentation } from '@grafana/faro-web-tracing';

initializeFaro({
  url: '/collect', // mesma origem, pelo main-alb: sem CORS
  app: { name: 'frontend', version: '1.0.0', environment: 'production' },
  instrumentations: [...getWebInstrumentations(), new TracingInstrumentation()],
});
```

Como o frontend e a API (`/api`) estão no mesmo host do ALB, as chamadas são de mesma origem e o `traceparent` é propagado sem configurar `propagateTraceHeaderCorsUrls`.

**No `main-alb`:** uma regra no listener `:80` para o caminho `/collect` → target group `faro-tg` (tipo `instance`, EC2 de observabilidade, porta `12347`). O ALB não reescreve caminhos, por isso o SDK usa o caminho padrão do receiver. Health check em `/-/ready` na porta `12345` (servidor HTTP do próprio Alloy).

**No Alloy:**

```alloy
faro.receiver "frontend" {
  server {
    listen_address           = "0.0.0.0"
    listen_port              = 12347
    max_allowed_payload_size = "1MiB"
    rate_limiting {
      rate       = 50
      burst_size = 100
    }
  }
  output {
    logs   = [loki.process.faro.receiver]
    traces = [otelcol.processor.batch.default.input] // mesmo caminho dos spans dos backends
  }
}

loki.process "faro" {
  stage.static_labels {
    values = {
      env     = "production",
      origin  = "frontend",
      service = "frontend",
    }
  }
  forward_to = [loki.write.default.receiver]
}
```

As linhas do Faro são logfmt, com o tipo em `kind` (`log`, `exception`, `measurement`, `event`) e, nas chamadas instrumentadas, o `trace_id`. Ficam na linha, como os campos do backend (seção 4.4):

```logql
{service="frontend"} | logfmt | kind="exception"
{service="frontend"} | logfmt | kind="measurement" | type="web-vitals"
```

O derived field da seção 5.6 procura `"trace_id":"..."` (JSON). Para as linhas do Faro, somar um derived field com `matcherRegex: 'trace_id=(\w+)'`.

No service graph, aparece a aresta `frontend → app`.

**Segurança:** este é o único endpoint de ingestão **público** da proposta. Qualquer pessoa pode enviar dados falsos, e uma chave no JavaScript não seria segredo. Mitigações:

- O `rate_limiting` e o `max_allowed_payload_size` do receiver.
- O WAF do `main-alb` já cobre `/collect`, incluindo o `BlockNonBrazilTraffic` e o rate limit por IP. As requisições do Faro somam ao limite por IP do usuário, mas o SDK agrupa os eventos em lotes, então o acréscimo é pequeno.
- Os dados recebidos só viram linhas de log e spans, sem ação automática. O risco aceito é ruído nos dados do frontend.

Liberar as portas `12347` e `12345` no security group da EC2 para o security group do ALB.

**Na demonstração:** o k6 não executa JavaScript, então o Faro não gera dados no teste de carga. Antes do ato 1, abrir o frontend no navegador, navegar por algumas telas e mostrar uma trace que começa em `frontend` (carregamento da página e `fetch`) e termina no `SELECT` do RDS.

### 18.6 Drilldown: exploração sem escrever query

Os apps **Drilldown** do Grafana (Logs, Metrics, Traces e Profiles) navegam pelos dados por cliques, sem LogQL, PromQL ou TraceQL. Eles vêm embutidos no Grafana (13.2 ou mais novo, sem plugin a instalar) e aparecem no menu **Drilldown**. Na apresentação, quem nunca viu LogQL consegue explorar os dados, e o time investiga mais rápido.

| App | O que mostra | Requisito |
|---|---|---|
| Logs Drilldown | Volume por label, **padrões** de log agrupados automaticamente (por exemplo, `Falha ao reservar estoque <_>` com contagem), detecção de `level` | Loki 3.2+ com pattern ingester e volume ligados |
| Metrics Drilldown | Todas as métricas do Mimir navegáveis por label, com prévia de gráfico | Nenhum (data source do tipo Prometheus) |
| Traces Drilldown | Taxa, erros e duração por qualquer atributo de span; comparação "lentas x normais" mostra quais atributos diferem | Tempo 2.6+ com TraceQL metrics |
| Profiles Drilldown | Flame graphs por serviço, comparação entre períodos | Pyroscope (seção 18.4) |

**Loki** (somar ao config):

```yaml
pattern_ingester:
  enabled: true
limits_config:
  allow_structured_metadata: true # exige schema v13 (tsdb)
  volume_enabled: true
  discover_log_levels: true       # lê o campo level do JSON do backend
```

**Tempo:** TraceQL metrics usa o processor `local-blocks` do metrics-generator (somar ao config da seção 17.1). Conferir a sintaxe na versão fixada do Tempo:

```yaml
metrics_generator:
  processor:
    local_blocks:
      flush_to_storage: true
  traces_storage:
    path: /var/tempo/generator/traces # volume no EBS
overrides:
  defaults:
    metrics_generator:
      processors: [service-graphs, span-metrics, local-blocks]
```

O `local-blocks` guarda as traces recentes em disco no Tempo para responder às consultas de métricas: medir a memória do container `tempo` depois de ligar.

**Na demonstração (ato 2):** em Logs Drilldown, o padrão de erro da publicação no RabbitMQ aparece como um novo grupo com contagem crescente. Em Traces Drilldown, a aba de comparação aponta o span do RabbitMQ como o atributo que separa as requisições com erro das demais, sem nenhuma query digitada.
