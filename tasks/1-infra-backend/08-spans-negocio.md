# 1.8 Spans de negócio

**Fase:** F4 (incremental) · **Repo:** backend · **Ref.:** § 5.4, § 8.1

## O que fazer

- [ ] Spans manuais só nos pontos de negócio relevantes: `PedidoService.criarPedido`, `EstoqueService.reservarEstoque`, `PagamentoService.autorizar`, regras complexas, integrações externas críticas.
- [ ] Opcional: atributos de negócio nos spans (ids, status), sem dados pessoais.

## Pronto quando

A trace mostra claramente `Controller → Service → Repository → Banco / Serviço externo`, sem spans triviais poluindo.
