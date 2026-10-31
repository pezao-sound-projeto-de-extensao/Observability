# 2.4 Leitor do CloudWatch: RDS e WAF

**Fase:** F1 · **Repo:** observabilidade (`cloudwatch-reader/`) · **Estimativa:** 3 h · **Ref.:** § 4.3, § 4.4, § 6.6

## Contexto

Sem Subscription Filter, Kinesis ou Lambda: polling direto na API do CloudWatch, feito por um leitor próprio em vez do `otelcol.receiver.awscloudwatch`, que perdeu eventos no lab (ver abaixo).

## O que fazer

- [x] Leitor em Python com boto3, um container no Compose, com a imagem gerada pelo Ansible.
- [x] Log groups por nome, com a origem fixa na config:
  - `/aws/rds/instance/app-db/error` e `/slowquery` → `origin="rds-logs"`, `lookback_seconds = 600`
  - `aws-waf-logs-main-alb-waf` → `origin="waf-logs"`, `lookback_seconds = 120`
- [x] Polling de 15 s: reler a janela recente e descartar pelo `eventId` o que já foi enviado.
- [x] Estado (progresso e IDs enviados) em volume no EBS. Sem estado, começar na última 1 h.
- [x] Enviar ao Alloy pela API de push do Loki, com as labels `env`, `origin`, `service` e `host` e o horário do evento: `alloy:3501` (RDS) e `alloy:3502` (WAF).
- [x] Do Alloy, seguir para `loki.write.default` e para o arquivo bruto (task 2.3).

## Testes locais

```bash
cd cloudwatch-reader
python -m unittest test_reader
```

Os 14 testes cobrem, com um CloudWatch falso: evento atrasado, evento isolado depois de janela vazia, paginação, falha de envio sem duplicar, retomada do estado e avanço conjunto dos grupos.

Também passaram em 2026-10-30, com o Alloy v1.21.3 real: `alloy validate` na config, e um push às portas 3501 e 3502 que chegou a um Loki falso com as 4 labels e a linha original.

## Resultado no lab (2026-10-31)

Comparação evento a evento entre o CloudWatch e o Loki, e contagem de linhas no `logs-raw`:

| Teste | Tráfego | Lido | Latência (evento → Loki) |
|---|---|---|---|
| WAF denso | 1 a cada 10 s | 18 de 18 | 16 a 32 s |
| WAF esparso | 1 a cada 40 s | 8 de 8 | 21 a 34 s |
| WAF isolado | 1 a cada 75 s | 5 de 5 | 14 a 31 s |
| RDS slow query | 1 a cada 40 s | 8 de 8 | 10 a 22 s |
| WAF sob carga | ~237 req/s por 1 min (30 conexões) | 14.303 de 14.303 no período | até 43 s |

- [x] **Retomada:** com a EC2 parada por 25 min, tudo chegou com o horário original (WAF 75/75 e RDS 63/63 no período), em ~30 s depois de o Alloy subir. `loki_write_dropped_entries_total` ficou em 0. O receiver chegou a 262 descartes nos testes de restart e parada.
- [x] **Restart do leitor:** levou 5 s, e o `logs-raw` não recebeu nenhuma linha repetida.
- [x] **Timestamp:** horário do evento no CloudWatch. Sem isso, as comparações exatas acima não fechariam.
- [x] **Imagem:** o `docker build` funcionou na EC2.
- [x] **Carga:** pico de 83 MiB de memória no leitor (limite de 256 MB) e de 21% de CPU, sem OOM e sem erro de throttling (a retentativa do boto3 não registra as esperas). Os ciclos subiram de ~15 para até ~26 s. O bloqueio apareceu nos logs: 14.278 linhas com `"action":"BLOCK"` no `logs-raw`, nenhuma repetida.
- [x] **IAM:** a `LabRole` leu os log groups sem erro.

**O que não foi medido:**
- **Error log do RDS:** eventos reais só no boot (entregues em até 138 s) e um aviso, lido 10 s depois. Senha errada não vai para esse log. A estimativa de até ~2,5 min é a entrega medida mais o polling.
- **Carga:** o teste usou um script Python com 30 conexões, não o k6. Sem o app, o ALB respondeu 403 e 429.
- **Live Tail:** o leitor não foi conferido no navegador.

## Limites conhecidos

- **Atraso maior que o `lookback_seconds`:** o evento não é lido. Aumentar a janela custa mais chamadas à API e mais tráfego no NAT.
- **Consulta grande no Loki:** 5.000 linhas de WAF (~1,6 KB cada) passavam do limite de gRPC do Loki (4 MB por padrão), e a consulta dava erro depois de 60 s. Com o limite em 16 MB, ela responde em 0,5 s (11,8 MB de JSON). 5.000 é o máximo de linhas por consulta no Loki por padrão.
- **Queda entre o envio e a gravação do estado:** o último ciclo é reenviado. O Loki não duplica (mesmo horário e mesma linha), mas o `logs-raw` sim.
- **Sem métricas próprias:** uma falha só aparece em `docker compose logs cloudwatch-reader`. Se RDS ou WAF pararem de chegar ao Grafana, conferir ali.

## Por que não o `otelcol.receiver.awscloudwatch`

O receiver (v0.162.0) filtra pelo horário do evento, sem margem para atraso. Quem chega ao CloudWatch depois que a janela passou nunca é lido. A janela seguinte começa logo após o último evento lido, mas pula para o horário atual em dois casos: quando vem vazia e, com `storage`, sempre, porque o checkpoint salvo é o horário atual.

| Checkpoint | `poll_interval` | Tráfego | WAF lido |
|---|---|---|---|
| Com | `10s` | 1 a cada 10 s | 0 de 24 |
| Com | `60s` | 1 a cada 10 s | 29 de 36 |
| Sem | `10s` | 1 a cada 10 s | 0 de 24 |
| Sem | `10s` | 1 a cada 40 s | 0 de 10 |
| Sem | `60s` | 1 a cada 10 s | 36 de 36 |
| Sem | `60s` | 1 a cada 75 s | 14 de 14 |

O atraso de entrega do WAF foi de 7 a 24 s; no RDS, ~3 s no slow query e 5 a 141 s no error log.

A melhor combinação (sem checkpoint, 60 s) ainda tinha estes custos:
- **Evento isolado:** pelo código, um evento no fim de uma janela vazia ainda se perde.
- **Restart:** cada restart, ou reload que recrie o receiver, relia o log group inteiro (até 3 dias). O Loki recusou o que tinha mais de 1 h em relação ao mais novo do stream (262 em `loki_write_dropped_entries_total`), e o `logs-raw` recebia tudo de novo.
- **Falha no STS:** o receiver chama `sts:GetCallerIdentity` ao iniciar, ignora o erro e acessa o resultado. Sem credenciais ou sem rota até o STS, o **processo inteiro** do Alloy caía com um panic (`ensureSession`), parando logs, traces e métricas.

## Pronto quando

`{origin="waf-logs"} |= "BLOCK"` e `{origin="rds-logs"}` retornam dados, e os itens de validação no lab estão documentados (ver o resultado acima).
