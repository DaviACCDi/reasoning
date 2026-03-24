# Binary Local Production Pipeline

Pipeline local para produzir dataset do dominio `binary` de forma configuravel e auditavel.

## Comando principal

```bash
python jobs/domains/binary/run_binary_domain.py --total 10000 --run-id binary_run_001 --model llama3.1:8b --export-csv --export-jsonl
```

## Runner de conveniencia

```bash
./scripts/run_binary_dataset.sh --total 10000 --run-id binary_run_001 --model llama3.1:8b --export-csv --export-jsonl
```

## Parametros suportados

- `--total`
- `--model`
- `--distribution-file`
- `--mixed-config`
- `--output-root`
- `--run-id`
- `--seed`
- `--batch-size`
- `--thresholds-file`
- `--export-csv`
- `--export-jsonl`

## Estrutura de output por execucao

- `data/domains/binary/runs/<run_id>/generated/`
- `data/domains/binary/runs/<run_id>/validated/`
- `data/domains/binary/runs/<run_id>/approved/`
- `data/domains/binary/runs/<run_id>/rejected/`
- `data/domains/binary/runs/<run_id>/final/`
- `data/domains/binary/runs/<run_id>/reports/`

## Arquivos finais principais

- `data/domains/binary/runs/<run_id>/final/binary_train_ready.csv`
- `data/domains/binary/runs/<run_id>/final/binary_train_ready.jsonl`

Schema final:

- `id`
- `prompt`
- `answer`

## Relatorios gerados

- `reports/generation_summary.json`
- `reports/quality_report.json`
- `reports/distribution_report.json`
- `reports/rejection_report.json`
- `reports/run_summary.json`

## Deliverable latest

- `deliverables/binary/latest/binary_train_ready.csv`
- `deliverables/binary/latest/binary_train_ready.jsonl`
