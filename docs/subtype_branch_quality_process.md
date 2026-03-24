# Subtype Branch Quality Process

Este projeto usa isolamento por subtipo com merge baseado em qualidade comprovada.

## Branch strategy

- Base branch: `main`
- Uma branch por subtipo: `feature/<problem_type>-<subgroup>`
- Exemplo inicial: `feature/binary-shift`

## Mandatory loop per subtype

1. Ajustar prompt do subtipo
2. Gerar lote pequeno
3. Validar semanticamente
4. Aplicar scoring
5. Analisar erros (keep/review/reject)
6. Recalibrar prompt e thresholds
7. Repetir ate estabilidade
8. Escalar volume (3k+)
9. Preparar dataset final
10. Abrir PR com evidencias

## Quality gate (minimum)

- Keep rate >= 0.90
- Reject rate <= 0.05
- Semantic valid rate >= 0.95
- Average score >= 0.95

## PR checklist

- Descricao do subtipo
- Estrategia de prompt
- Metricas de qualidade
- Exemplos bons e ruins
- Taxa keep/reject
- Falhas principais e mitigacoes
- Evidencia de exportacao para formato train
