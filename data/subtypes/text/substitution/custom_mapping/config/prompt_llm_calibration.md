# Calibração LLM — custom_mapping

Base operacional do código: branch `feature/text-substitution-foundation`.  
Calibração com modelo local: branch `feature/text-substitution-custom-mapping` (ou trabalho local até PR).

## Modos do orquestrador

- `--llm-role none` — baseline programático (smoke / sem Ollama).
- `--llm-role reasoning` — Ollama devolve só JSON `{"reasoning":"..."}`; `problem` e `final_answer` são programáticos (aderência ao train).
- `--llm-role phrases` — Ollama devolve `examples_plain` + `query_plain`; cifragem e resposta são programáticas; validador rejeita formato inválido.

## Comando típico (Ollama em 127.0.0.1:11434)

```bash
python jobs/subtypes/orchestrate_text_substitution_subtypes.py \
  --subtypes custom_mapping \
  --model llama3.1:8b \
  --llm-role phrases \
  --batch-size 40 \
  --max-iterations 8 \
  --seed 42
```

Ajustar prompts no código (`llm_phrases_custom_mapping`, `llm_reasoning_only`) e iterar até `raw_parse_success_rate` e gates de qualidade estabilizarem.
