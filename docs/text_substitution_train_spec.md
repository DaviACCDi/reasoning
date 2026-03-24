# text/substitution — especificação de referência (train.csv)

Referência: linhas de `data/raw/train.csv` cujo `prompt` contém  
`secret encryption rules are used on text`.

## Cabeçalho fixo

```
In Alice's Wonderland, secret encryption rules are used on text. Here are some examples:
```

## Corpo

- Uma ou mais linhas de exemplo no formato:

```
<ciphertext com letras minúsculas e espaços> -> <plaintext com letras minúsculas e espaços>
```

- Os comprimentos de `ciphertext` e `plaintext` **coincidem carácter a carácter** (incluindo espaços nas mesmas posições).

## Tarefa

- Linha final:

```
Now, decrypt the following text: <ciphertext da query>
```

- No conjunto analisado, a tarefa é **sempre decrypt** (não há variante encrypt isolada no raw).

## Resposta (`answer`)

- Texto em minúsculas, palavras separadas por espaço (como no train).
- **Sem** `\boxed{}` no CSV oficial.

## Implicações para geração

- O mapa letra↔letra é **implícito pelos exemplos** (monoalfabético nas letras observadas).
- Subtipos operacionais (`caesar_shift`, `reverse_alphabet`, etc.) são **eixos de produção**; só `custom_mapping` reflete diretamente a diversidade empírica das 1576 linhas do train.

## Artefatos

- Estatísticas agregadas: `data/subtypes/text/substitution/_shared/reports/train_reference_stats.json` (gerado por `jobs/subtypes/extract_text_substitution_train_stats.py`).
