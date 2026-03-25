# ADR Rules

When creating or modifying ADRs under this directory, follow the rules below.

## Scope

- These rules apply to all ADR documents under `docs/adr/`.
- Primary managed files are:
  - `_template.md`: ADR body template
  - `000_index.md`: ADR index for all records
  - `NNN_*.md`: actual ADR documents

## Architecture Discussion Handling

- If the user asks about architecture, design, technology selection, trade-offs, structural changes, or similar, check `docs/adr/000_index.md` and relevant ADRs first.
- If relevant ADRs exist, determine whether the request follows existing decisions, complements them, or changes them.
- If no relevant ADR exists, treat the request as an undecided point requiring explicit decision handling.
- If a request conflicts with existing ADRs or changes direction, state that clearly in the response or plan.
- If the discussion leads to a long-term decision worth remembering, propose creating or updating an ADR.

## Writing Principles

- New ADRs must start by copying `docs/adr/_template.md`.
- Replace all `{{ ... }}` placeholders in the template.
- Final ADRs must not keep any `{{` or `}}`.
- ADR body should be entirely in Korean.
- `Status` must also be in Korean. Example: `채택`, `대체됨`, `ADR 003 대체`.
- `1. Title` should contain a human-readable formal title.
- Unless explicitly requested, do not edit `_template.md` itself.

## Filename Rules

- ADR filename format is fixed as `NNN_Korean_Title_Summary.md`.
- `NNN` is always three digits. Example: `001_로그인_세션_전략.md`
- Keep title summaries in Korean; replace spaces with `_`.
- Do not add unnecessary special characters.
- Exclude `000_index.md`, `_template.md`, and `AGENTS.md` when calculating the next number.
- If no real ADR exists, numbering starts from `001`.

## Index Rules

- When creating a new ADR or changing title/status/filename of an existing one, update `docs/adr/000_index.md` together.
- `000_index.md` is a quick architecture decision list for reviewers.
- Keep index format as this table:

```md
| 번호 | 제목 | 상태 | 링크 |
| --- | --- | --- | --- |
| 001 | 로그인 세션 전략 | 채택 | [NNN_Korean_Title_Summary.md](./NNN_Korean_Title_Summary.md) |
```

- Index rows must be sorted by number ascending.
- `제목` in index must match `Title` in ADR body.
- `상태` in index must match `Status` in ADR body.
- If an ADR supersedes another ADR, do not add only the new ADR; update related existing statuses as needed.

## ADR Creation Procedure

1. Check existing ADR files and determine next three-digit number.
2. Copy `_template.md` to new file `NNN_Korean_Title_Summary.md`.
3. Replace all `{{ ... }}` placeholders with actual Korean content.
4. Fill `Title`, `Status`, `Context`, `Decision`, and `Consequences`.
5. Add/update index row in `000_index.md` with number, title, status, and link.
6. Verify no placeholders remain in final document.

## Final Checklist

- Filename follows `NNN_Korean_Title_Summary.md` format.
- Number is the next sequence.
- ADR body is written in Korean.
- All placeholders are removed.
- `000_index.md` is kept up to date.
- Index title/status/link matches ADR body and filename.
