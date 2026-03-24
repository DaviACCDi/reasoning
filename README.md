# Reasoning Factory (Fixed Taxonomy)

Arquitetura orientada por subtipo para operar um subtipo por vez, sem descoberta dinamica.

## Estrutura base

- `data/raw/train.csv`
- `data/raw/test.csv`

## Taxonomia oficial (fixa)

- `binary/shift` (1602)
- `logic/formula` (1597)
- `logic/mapping` (1594)
- `logic/roman` (1576)
- `logic/symbolic` (1555)
- `text/substitution/*` (1576 no total; ver variantes abaixo)

Variantes operacionais sob `data/subtypes/text/substitution/<variant>/` (manifesto em `data/taxonomy/taxonomy_manifest.json`):

- `custom_mapping` — ancora do train (1576 linhas no raw)
- `caesar_shift`, `reverse_alphabet`, `number_mapping`, `mixed` — extensoes sinteticas (0 linhas isoladas no raw)

Total observado no raw: `9500`.

## Job unico de taxonomy

```bash
python jobs/taxonomy/create_taxonomy_structure.py
```

Esse script:

1. Define a taxonomia oficial em codigo (hardcoded).
2. Cria a estrutura `data/subtypes/<problem_type>/<subgroup>/...` (texto: `text/substitution/<variant>/...` + `_shared/`).
3. Gera manifesto estatico em `data/taxonomy/taxonomy_manifest.json` (opcional).

## Estrutura por subtipo

Para cada subtipo, cria:

- `source/`
- `generated/`
- `validated/`
- `reviewed/`
- `rejected/`
- `final/`
- `reports/`
- `config/`

## Operacao por subtipo

Fluxo recomendado:

1. Escolher um subtipo.
2. Gerar dados em `generated/`.
3. Validar qualidade em `validated/`.
4. Separar `reviewed/`, `rejected/` e `final/`.
5. Consolidar metricas em `reports/`.

## Git and branch workflow

- Repositorio com branch principal `main`.
- Desenvolvimento por subtipo em branches `feature/<problem_type>-<subgroup>`.
- Primeiro subtipo ativo: `feature/binary-shift`.

## Primeiro subtipo: binary/shift

Arquivos principais:

- `jobs/subtypes/binary_shift_pipeline.py`
- `data/subtypes/binary/shift/config/prompt_v1.md`
- `data/subtypes/binary/shift/config/quality_thresholds.json`

Executar lote de calibracao:

```bash
python jobs/subtypes/binary_shift_pipeline.py --batch-size 200 --seed 42
```

Saidas geradas:

- `data/subtypes/binary/shift/generated/candidates.jsonl`
- `data/subtypes/binary/shift/validated/validated.jsonl`
- `data/subtypes/binary/shift/reviewed/keep.jsonl`
- `data/subtypes/binary/shift/reviewed/review.jsonl`
- `data/subtypes/binary/shift/rejected/reject.jsonl`
- `data/subtypes/binary/shift/final/train_ready.jsonl`
- `data/subtypes/binary/shift/reports/quality_report.json`

Gate de merge por qualidade:

- Keep rate >= 0.90
- Reject rate <= 0.05
- Semantic valid rate >= 0.95
- Average score >= 0.95

Processo de PR e qualidade:

- `docs/subtype_branch_quality_process.md`
- `.github/pull_request_template.md`

## Dominio text/substitution (calibracao)

Especificacao do bloco no train: `docs/text_substitution_train_spec.md`.

Estatisticas de referencia (geradas):

```bash
python jobs/subtypes/extract_text_substitution_train_stats.py
```

Orquestrador por variante (geracao + validacao programaticas no estilo train; calibracao com modelo local nas iteracoes seguintes):

```bash
python jobs/subtypes/orchestrate_text_substitution_subtypes.py --batch-size 100 --max-iterations 5 --subtypes custom_mapping
python jobs/subtypes/orchestrate_text_substitution_subtypes.py --subtypes all
```

Relatorio agregado: `data/subtypes/text/substitution/_shared/reports/orchestrator_report.json`.
