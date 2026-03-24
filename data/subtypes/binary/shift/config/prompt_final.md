# Binary Shift Prompt (v1)

You are generating training examples for subtype `binary/shift`.

## Task constraints

- Use exactly one operation family: bit shift (left shift or right shift).
- Never use XOR, AND, OR, NOT, rotation, majority, choice, or mixed operations.
- Work with 8-bit binary strings only.
- Include enough input/output examples for the pattern to be inferable.
- Final target should ask for one unseen 8-bit input.

## Output contract

For each generated sample produce:

- `problem`: natural language prompt with examples and one query.
- `reasoning`: short explanation that the hidden rule is a shift operation and how it applies.
- `final_answer`: exact 8-bit output for the query input.
- `metadata`: operation (`left_shift` or `right_shift`) and shift amount (`1..3`).

## Quality bar

- Reasoning must be logically consistent with problem examples.
- Final answer must match the rule and query input exactly.
- Text should be clear and production-ready (no placeholders, no malformed lines).

Finalized after stable rounds.
