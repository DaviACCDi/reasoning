# text/substitution — foundation vs calibração por subtipo

## Branch foundation (base operacional)

- **Branch:** `feature/text-substitution-foundation`
- **Papel:** estrutura de pastas, manifesto, estatísticas do train, orquestrador com geração **programática** de referência, validadores e smoke de gates.
- **Não significa:** domínio fechado para produção nem excelência com modelo local.

Tudo o que for calibração “de verdade” com **llama3.1:8b** deve partir desta base (merge ou branch filha), subtipo a subtipo.

## Branches de subtipo (calibração + PR)

Cada variante tem uma branch dedicada, nesta ordem:

| Ordem | Subtipo | Branch sugerida |
|------|---------|-----------------|
| 1 | `text/substitution/custom_mapping` | `feature/text-substitution-custom-mapping` |
| 2 | `text/substitution/reverse_alphabet` | `feature/text-substitution-reverse-alphabet` |
| 3 | `text/substitution/caesar_shift` | `feature/text-substitution-caesar-shift` |
| 4 | `text/substitution/number_mapping` | `feature/text-substitution-number-mapping` |
| 5 | `text/substitution/mixed` | `feature/text-substitution-mixed` |

### Abrir uma branch de subtipo a partir da foundation

```bash
git fetch origin
git checkout feature/text-substitution-foundation
git pull origin feature/text-substitution-foundation
git checkout -b feature/text-substitution-<kebab-name>
```

Substituir `<kebab-name>` por `custom-mapping`, `reverse-alphabet`, etc.

Script de conveniência: `scripts/create_text_substitution_subtype_branches.sh` (lista comandos para todas as branches).

## Critério de “subtipo pronto”

Um subtipo **não** está concluído só porque:

- o pipeline corre,
- o parser funciona,
- o smoke programático passou.

Está concluído quando, **com llama3.1:8b** (e prompts/limiares finais):

- a qualidade do output for consistentemente alta,
- a aderência ao `train.csv` estiver documentada (comprimento, estrutura, estilo),
- os relatórios de iteração mostrarem estabilidade sob lotes maiores.

## Orquestrador

- Programático (baseline): `python jobs/subtypes/orchestrate_text_substitution_subtypes.py --subtypes <variant> --llm-role none`
- Calibração `custom_mapping` com modelo local:
  - `--llm-role reasoning` — só gera `reasoning` em JSON; `problem` e `final_answer` permanecem programáticos.
  - `--llm-role phrases` — modelo propõe plaintexts das frases-exemplo e da query; cifragem e resposta finais são programáticas; validação rejeita formato inválido.

Requer Ollama em `http://127.0.0.1:11434` com o modelo indicado em `--model`.
