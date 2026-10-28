# 1.9 Reavaliar access logs do ALB

**Fase:** F4 · **Repo:** infra · **Ref.:** § 12

## Contexto

Hoje não são coletados: o roteamento é simples, e logs e traces dos backends já cobrem a investigação.

## Quando fazer

Se surgir necessidade de investigar 5xx vistos pelo cliente, padrões de tráfego, abuso ou incidentes de segurança.

## O que fazer (se aprovado)

- [ ] Habilitar o access log do ALB para S3.
- [ ] Integrar ao pipeline (tabela no Athena ou leitura pelo Alloy), sem mudar o resto.
