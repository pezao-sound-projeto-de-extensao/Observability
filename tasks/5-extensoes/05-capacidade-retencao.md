# 5.5 Capacidade, retenção e sampling

**Fase:** F4 (contínua) · **Repo:** observabilidade · **Ref.:** § 6.4, § 6.7, § 7, § 13

## O que fazer

- [ ] Revisar `mem_limit` com base no uso real (dashboard de saúde, task 4.4).
- [ ] Ajustar retenções (Loki 7 d, Tempo 7 d, Mimir 15 d, Pyroscope 7 d, bruto 30 d) conforme custo e uso.
- [ ] Se o volume de traces pesar: tail sampling no Alloy (100% de erros e lentas, amostra das demais), **não** reduzir o sampling no agente.
- [ ] Se o volume justificar: Loki *simple scalable*, EC2 separadas ou ECS (fora do lab), Mimir com réplicas.
- [ ] Barramento de logs só volta a fazer sentido com vários consumidores ou necessidade de replay.
