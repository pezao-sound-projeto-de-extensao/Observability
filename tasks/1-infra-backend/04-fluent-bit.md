# 1.4 Fluent Bit: deploy e métricas

**Fase:** F1 (logs), F3 (métricas) · **Repo:** infra (`DevOps`, Ansible dos nós app) · **Estimativa:** 2 h · **Ref.:** § 4.2, § 4.5, § 18.3

## Contexto

**Já feito e testado localmente (2026-10-26):** `fluent-bit.conf.j2` com output `loki`, buffer em disco e `scheduler.cap 60`; volume `fluent-bit-buffer` e `fluentd-sub-second-precision: "true"` no `docker-compose.yml.j2`; `otel_endpoint_ip` no lugar de `kinesis_stream`.

## O que fazer

### F1: deploy
- [ ] Definir `otel_endpoint_ip` com o IP fixo da task 1.2.
- [ ] Aplicar Terraform/Ansible.
- [ ] Conferir no nó app: `storage.path` montado, `retry_limit no_limits`, `storage.total_limit_size 1G`, `label_keys $env,$origin,$service,$host`, `line_format json`.

### F3: métricas do próprio Fluent Bit (push)
- [ ] Somar ao `fluent-bit.conf.j2`:
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
- [x] Listar os nomes das métricas geradas na versão 3.2 e passar para quem faz os alertas (task 4.4).

## Pronto quando

- Sem a stack no ar, os chunks se acumulam em `/fluent-bit/buffer` sem descarte; com o Alloy no ar (task 2.3), são entregues com o horário original.
- `fluentbit_output_retries_total` aparece no Mimir.
