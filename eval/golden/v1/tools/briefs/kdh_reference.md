# Reference checks for VBP requirements (paket 1b, stage 5)

You turn official test procedures into reference checks for an evaluation dataset. A test writer
who never sees your output will later write tests from the requirement text (with or without
corpus passages); a judge will mark each of your checks as covered or not. Recall is weighted by
check, so the checks must be fair: things the requirement asks for, observable by running the
system (VBP, a citizen application portal; see corpus/text/VBP-*.txt).

## Files (work only here)

- `refs/<ID>.json`: the requirement (`text`, `language`, `source`, `stratum`, `reference_origin`)
  and `reference_blocks`, verbatim official procedure text by source:
  - NIST SP 800-63-4 conformance criteria (doc `NIST-800-63-4-CC`): statement, objective and
    assessment methods (TEST / EXAMINE / INTERVIEW prose).
  - W3C ACT rules (doc `W3C-ACT-RULES`): Applicability, Expectation, assumptions, test cases.
  - Rehber audit table window (doc `SGB-REHBER-1.1`): measure numbers, names, audit method
    suggestions and audit questions between the previous and the next measure. In this text one
    or more questions of a row can appear BEFORE its measure number; decide by content which
    questions belong to the requirement's measure.
  - NIST 800-53 Rev.5.2.0 (doc `NIST-SP-800-53r5`): statement items, assessment objectives and
    methods; organisation-defined parameters appear as [label].
  - none (ASVS and system-specific requirements, reference_origin "claude").
- `corpus/text/`: the documents the test writer may see: NIST 800-63-4 volumes, ASVS CSV, WCAG
  2.2, Rehber (audit tables removed) and 800-53 (assessment parts removed) writer views, Denetim
  Rehberi, GOV.UK pages, and the VBP system documents VBP-KIB-001, VBP-PYP-001, VBP-YTB-001.
- Do not open anything else (no /home/user/testmentor, no generated tests, no other directories).
  No web. Do not commit.

## Rules

1. **One observable outcome per check.** `action` = the situation or stimulus a tester creates on
   VBP; `expected` = ONE observable outcome. Write checks in the requirement's language (Turkish
   requirement → Turkish checks).
2. **Only what can be tested by running VBP.** Turn TEST procedures, ACT expectations, Rehber
   questions answerable by Sızma Testi / Güvenlik Denetimi, and 800-53 objectives that a TEST can
   show into checks. Decide by whether the behaviour can be observed by running VBP, not by the
   wording: "CORS güvenlik önlemleri tanımlanmış mıdır?" or "oturum sonlandığında ... test edilmiş
   midir?" become checks of the behaviour itself. Items that can only be answered from policies,
   documents or interviews (EXAMINE / INTERVIEW, "politika/prosedür var mıdır", "kim sorumludur")
   are not checks; count them in `reference_note`.
3. **Scope.** Keep a check only if the requirement text states that behaviour (the requirement
   may cover only part of a measure or criterion). Count dropped items in `reference_note`. If no
   check survives, output empty `reference_checks` and explain; do not substitute your own.
   Parts of the requirement that no official procedure item covers get no check either; list
   them in `reference_note` as "uncovered: ..." so they can be reported separately.
4. **Generality.** `action` states the distinguishing condition at the requirement's level of
   generality. Concrete values belong in a check when the requirement or a VBP document fixes
   them (e.g. the lockout threshold from VBP-YTB-001 §14) — such a check needs documents.
   Put tool or channel detail (specific scanner, header dump, screen reader name) in
   `channel_note`, not in `expected`.
5. **Size.** At most 6 checks per requirement; merge repeats; prefer checks that separate correct
   from incorrect behaviour (include the negative case when the procedure has one).
6. **Basis.** For official requirements every check has
   `basis = {doc, ref, text}`: doc as listed above, ref = criterion id / ACT rule id / measure
   number / control id, and `text` copied verbatim from the block (whitespace may differ; join
   non-contiguous pieces with " … "; for 800-53 do not quote across a [parameter] placeholder —
   split around it with " … "). Do not paraphrase inside `basis.text`. When you merge items from
   several rules/criteria into one check, quote the primary one in `basis` and name the merged
   ids in `channel_note` ("merged: ACT 6cfa84"). For "claude" requirements
   `basis` is null and you write at most 4 checks from the standard text and the VBP documents.
7. **Preconditions.** `reference_preconditions`: the starting state needed (account types, AAL,
   test data), one short paragraph, in the requirement's language.
8. **Support passages.** For each check, the corpus text a test writer needs (standard clause,
   VBP design decision or parameter row). Copy verbatim from `corpus/text/` (one contiguous piece
   per passage, up to ~800 characters; whitespace may differ). `doc` = the document id: file name
   without `.txt` and without `.writer` (e.g. "SGB-REHBER-1.1", "NIST-SP-800-53r5",
   "VBP-YTB-001", "W3C-WCAG-2.2"; GOV.UK files → "GOVUK-SERVICE-STANDARD"). Ids `<ID>-P1`, ...;
   list them in each check's `passages`. If an expected result relies on text not in
   `corpus/text/`, set `not_in_corpus: true`.
9. **Document need.** `needs_documents` per check: true if a competent tester could NOT write it
   from the requirement text alone (needs a value, list, rule, decision or definition found only
   in the documents). Requirement-level `needs_documents` = any check true. Be honest.
10. **Defects.** Never rewrite the requirement. Report misstatements or design gaps in
   `reference_note`.

## Output

`out/<ID>.refs.json`:
```json
{"id": "...", "reference_preconditions": "...",
 "reference_checks": [{"action": "...", "expected": "...", "channel_note": "",
   "basis": {"doc": "NIST-800-63-4-CC", "ref": "PV-3", "text": "..."},
   "passages": ["ID-P1"], "needs_documents": true, "not_in_corpus": false}],
 "support_passages": [{"id": "ID-P1", "doc": "NIST-SP-800-63B-4", "section": "3.1.1.2", "text": "..."}],
 "needs_documents": true, "reference_note": "..."}
```
Validate with a script that each file parses, every passage `text` occurs in its corpus file and
every `basis.text` piece occurs in the reference block after collapsing whitespace; fix failures.

## Batches

Your batch file lists your requirement ids, one per line; process all of them.
