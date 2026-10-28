# 5.1 Profiling contínuo com Pyroscope

**Fase:** F3 · **Repo:** observabilidade · **Estimativa:** 3 h · **Ref.:** § 18.4 · **Depende de:** 1.7 (extensão no backend)

## Contexto

A trace mostra qual span demorou; o profile mostra qual método dentro dele. Com span profiles, cada span ganha um botão **Profiles** no Tempo.

```text
Backends (extensão pyroscope-otel) ──> Alloy :4040 ──> Pyroscope ──> S3
```

## O que fazer

### Alloy
- [ ] `pyroscope.receive_http "backends"` na porta 4040 → `pyroscope.write "default"` para `http://pyroscope:4040`.

### Pyroscope
- [ ] Container `grafana/pyroscope` monolítico, versão fixada, `mem_limit: 768m`, volume em `/data`. Porta só na rede do Compose.
- [ ] S3 `pyroscope-profiles` com `native_aws_auth_enabled: true` (sem chaves).
- [ ] Retenção 7 dias (conferir a opção na versão; na v1, `limits.compactor_blocks_retention_period: 7d`).

### Grafana
- [ ] Data source `grafana-pyroscope-datasource`, `uid: pyroscope`, `url: http://pyroscope:4040`.
- [ ] No data source Tempo:
  ```yaml
  tracesToProfiles:
    datasourceUid: pyroscope
    profileTypeId: process_cpu:cpu:nanoseconds:cpu:nanoseconds
    tags:
      - key: service.name
        value: service_name
  ```

## Atenção

Spans mais curtos que 10 ms podem ficar sem amostras; os lentos, que interessam, têm.

## Pronto quando

Em um span do controller, **Profiles** abre o flame graph (Jackson, Hibernate, espera no JDBC).
