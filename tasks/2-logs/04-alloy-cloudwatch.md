# 2.4 Alloy: RDS e WAF via CloudWatch

**Fase:** F1 · **Repo:** observabilidade · **Estimativa:** 3 h · **Ref.:** § 4.3, § 4.4, § 6.6

## Contexto

Sem Subscription Filter, Kinesis ou Lambda: polling direto na API do CloudWatch. Custo: até ~1,5 min de atraso.

## O que fazer

- [ ] Um `otelcol.receiver.awscloudwatch` **por origem**, log groups por nome (bloco `named`):
  - `/aws/rds/instance/app-db/error` e `/slowquery` → `origin="rds-logs"`
  - `aws-waf-logs-main-alb-waf` → `origin="waf-logs"`
- [ ] `poll_interval = "60s"` e **sem** `otelcol.storage.file` (decisão de 2026-10-30, ver a perda de eventos abaixo).
- [ ] Promover `env`, `origin`, `service`, `host` com `loki.resource.labels` / `loki.attribute.labels` → `otelcol.exporter.loki` → `loki.write.default`.
- [ ] Enviar também ao arquivo bruto (task 2.3).
- [ ] Conferir no policy simulator: `logs:FilterLogEvents`, `logs:DescribeLogGroups`, `logs:DescribeLogStreams` na `LabRole`.

## Validar no lab (não documentado pelo Alloy)

- [ ] **Retomada:** parar a EC2, gerar logs, religar. Retoma de onde parou? Se não, ajustar `initial_lookback` (teto: 3 dias).
- [ ] **Timestamp:** horário do evento no CloudWatch, não o da leitura.

**Resultado no lab (2026-10-30, Alloy v1.21.3):**
- **Retomada (já sem checkpoint):** com a EC2 parada por ~2 min, nada se perdeu: 6/6 eventos do WAF e 1/1 do RDS chegaram depois de religar. O teste foi só com esses eventos de uma parada curta.
- **Timestamp:** horário do evento no CloudWatch, conferido em 29/29 eventos do WAF.
- **IAM:** a `LabRole` leu os log groups sem erro; o policy simulator não foi usado.

## Por que sem checkpoint e com 60 s: o receiver perde eventos atrasados

O `awscloudwatchreceiver` (v0.162.0) filtra pelo horário do evento, sem margem para atraso. Quem chega ao CloudWatch depois que a janela passou nunca é lido. A janela seguinte começa logo após o último evento lido, mas pula para o horário atual em dois casos: quando vem vazia e, com `storage`, sempre, porque o checkpoint salvo é o horário atual. Por isso, a config usa `60s` e não tem `storage`.

| Checkpoint | `poll_interval` | Tráfego | WAF lido |
|---|---|---|---|
| Com | `10s` | 1 a cada 10 s | 0 de 24 |
| Com | `60s` | 1 a cada 10 s | 29 de 36 |
| Sem | `10s` | 1 a cada 10 s | 0 de 24 |
| Sem | `10s` | 1 a cada 40 s | 0 de 10 |
| Sem | `60s` | 1 a cada 10 s | 36 de 36 |
| Sem | `60s` | 1 a cada 75 s | 14 de 14 |

O atraso de entrega do WAF foi de 7 a 24 s. O RDS está sujeito à mesma falha: ~3 s no slow query e 5 a 141 s no error log, sem medição de perda.

**Limite do teste:** a 75 s, os eventos só caíram em 4 pontos da janela de 60 s, então o caso de evento isolado no fim de uma janela vazia pode não ter sido exercitado. Pelo código, ele ainda perde o evento.

**Custos de tirar o checkpoint (medidos em restart do Alloy):**
- Cada restart, ou reload que recrie o receiver, relê o log group inteiro (até 3 dias). Os eventos perdidos na última hora voltaram: 10 de 10.
- O Loki não duplicou (mesmo horário e mesma linha), mas recusou o que tinha mais de 1 h em relação ao mais novo do stream: 241 registros em `loki_write_dropped_entries_total`, com `reason="ingester_error"`. Isso afeta os alertas da task 4.4.
- O `logs-raw` recebe tudo de novo, então o Athena vai precisar de `SELECT DISTINCT`.

**Alternativa, se a perda ou o atraso virarem problema:** um leitor próprio que releia uma janela recente e remova duplicados pelo ID do evento. Ele também eliminaria a falha no STS descrita abaixo.

## Risco: falha no STS derruba o Alloy

O `awscloudwatchreceiver` (v0.162.0) chama `sts:GetCallerIdentity` ao iniciar a sessão, ignora o erro e acessa o resultado. Se a chamada falhar (sem credenciais ou sem rota até o STS), o **processo inteiro** do Alloy cai com um panic, reproduzido no teste local. O `restart: unless-stopped` o religa, mas ele entra em loop enquanto a causa durar, parando logs, traces e métricas. Se o Alloy reiniciar sem parar, procurar `ensureSession` no log e conferir o NAT e o metadata da instância.

## Pronto quando

`{origin="waf-logs"} |= "BLOCK"` e `{origin="rds-logs"}` retornam dados, e os dois itens de validação estão documentados.
