# 2.2 Loki

**Fase:** F1 · **Repo:** observabilidade · **Estimativa:** 4 h · **Ref.:** § 4.4, § 6.5

## O que fazer

- [ ] Loki monolítico, porta 3100 só na rede do Compose.
- [ ] Storage em `loki-logs`, credenciais do `LabInstanceProfile` (sem chaves).
- [ ] Schema v13 (tsdb).
- [ ] Retenção de 7 dias (sem isso o Loki nunca apaga):
  ```yaml
  limits_config:
    retention_period: 168h
  compactor:
    retention_enabled: true
    delete_request_store: s3
  ```
- [ ] WAL e cache em volume no EBS.

## Pronto quando

- Chunks gravados no S3; o WAL sobrevive a restart; compactor rodando com retenção.
