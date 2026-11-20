# Reference checks for ERTMS requirements (paket 1b, stage 5)

You turn official ERTMS test cases into reference checks for an evaluation dataset. A test writer
who never sees your output will later write tests from the requirement text (with or without
corpus passages); a judge will mark each of your checks as covered or not. Recall is weighted by
check, so the checks must be fair: things the requirement asks for, at behaviour level.

## Files (work only here)

- `refs/<ID>.json`: the requirement (`text`, `source.clauses`) and `reference_blocks`: verbatim
  official test cases from SUBSET-076-5-2 (IDENTIFICATION, Based on Requirements, METHOD OF TEST,
  STARTING CONDITIONS, SEQUENCE OF TEST with I(nput)/O(utput) rows, END CONDITIONS).
- `corpus/text/`: the documents the test writer may see (SUBSET-026 chapters, SUBSET-023
  glossary, SUBSET-027 JRU, ERA_ERTMS_015560 DMI, SUBSET-036/037-1/041/091).
- Do not open anything else (no /home/user/testmentor, no generated tests, no other directories).
  No web. Do not commit.

## Rules

1. **Checks from steps.** Walk the SEQUENCE OF TEST. An input step (I row: stimulus, situation)
   and the output rows that follow it form a check: `action` = the stimulus/situation in plain
   terms; `expected` = ONE observable outcome of the on-board unit at behaviour level (e.g. "the
   OBU sends a position report to the RBC that refers to BG1 as LRBG", "the OBU commands the
   service brake"). Split a step with several distinct outcomes into several checks.
2. **Behaviour core vs channel.** Interface detail goes to `channel_note`, never to `expected`:
   RTM/BTM message and packet numbers, variable values, JRU record names (NID_MESSAGE_JRU...), DMI
   symbol ids, test-bench instructions. `expected` must be judgeable for a test that observes the
   same behaviour through another channel. A step whose only output is the JRU recording of the
   stimulus itself is not a check (fold it into preconditions or drop it).
   The `action` states the distinguishing condition at the level of generality of the
   requirement (e.g. "information received by radio whose validity direction is opposite to the
   train orientation"), not the particular message or packet the official test happens to use;
   name that concrete message/packet in `channel_note` ("official test uses a conditional
   emergency stop message, M15"). Keep a concrete value in `action` only when the requirement or
   clause itself turns on it.
3. **Scope.** Tag each check with the SUBSET-026 clause it verifies (`clause`, e.g. "3.8.2.1.7").
   Keep a check only if (a) its clause is in the requirement's `source.clauses` and (b) the
   requirement text states that behaviour. Steps that only set up the scenario or verify other
   clauses are dropped; count them in `reference_note` ("dropped N steps: clauses ...").
4. **Size.** At most 6 checks per requirement. Merge checks that repeat the same outcome (same
   behaviour in alternative modes/levels, repeated cycles) into one. Prefer checks that
   distinguish correct from incorrect behaviour (the distinguishing condition must be in `action`).
5. **Basis.** Every check has `basis = {doc: "SUBSET-076-5-2", ref: "<feature>/TC<n>", text}`
   where `text` is copied verbatim from the block (the step row(s) you used; whitespace may
   differ; join non-contiguous pieces with " … "). Do not paraphrase inside `basis.text`.
6. **Preconditions.** `reference_preconditions`: the starting conditions needed, in plain terms
   (level, mode, session, stored data), one short paragraph.
7. **Support passages.** For each check, find the corpus text a test writer needs to write it
   (the SRS clause and anything it depends on: tables, variable definitions in SUBSET-026-7,
   message definitions in SUBSET-026-8, procedures in SUBSET-026-5). Copy verbatim from
   `corpus/text/` (one contiguous piece per passage, up to ~800 characters; whitespace may
   differ), give ids `<ID>-P1`, `<ID>-P2`..., `doc` = file name without `.txt` (e.g.
   "SUBSET-026-3"), `section` = clause number. List the passage ids in each check's `passages`.
   If the expected result depends on text that is not in `corpus/text/`, set
   `not_in_corpus: true` for that check.
8. **Document need.** `needs_documents` per check: true if a competent tester could NOT write
   that check (stimulus and outcome) from the requirement text alone — e.g. it needs a value,
   list, table, message, timer or rule defined only in the documents. Requirement-level
   `needs_documents` = any check true. Be honest: a check that follows directly from the
   requirement sentence is false.
9. **Defects.** Never rewrite the requirement. If its text misstates or omits what the clause
   and test cases show, say so in `reference_note`. If no check survives the scope rule, output an
   empty `reference_checks` and explain in `reference_note`.

## Output

`out/<ID>.refs.json`:
```json
{"id": "...", "reference_preconditions": "...",
 "reference_checks": [{"action": "...", "expected": "...", "clause": "...", "channel_note": "...",
   "basis": {"doc": "SUBSET-076-5-2", "ref": "...", "text": "..."},
   "passages": ["ID-P1"], "needs_documents": true, "not_in_corpus": false}],
 "support_passages": [{"id": "ID-P1", "doc": "SUBSET-026-3", "section": "...", "text": "..."}],
 "needs_documents": true, "reference_note": "..."}
```
Validate that each file parses, that every `basis.text` and passage `text` occurs in its source
file after collapsing whitespace (write a small script), and fix any that do not.

## Requirements without official blocks

If `reference_blocks` is empty (reference_origin "claude"), write at most 4 checks yourself from
the clause in `corpus/text/SUBSET-026-3.txt` and the rules above, with `basis: null` and no
`clause` outside `source.clauses`. For `non_testable` requirements (Table 3 of SUBSET-076-7 lists
them as not or only partially testable on a test bench) write checks only for the part that can
be observed by running the OBU; if none can, output empty `reference_checks` and explain.

## Batches

Your batch file `batchN.txt` lists your requirement ids, one per line; process all of them and
write one `out/<ID>.refs.json` per id. Do not open other batches' outputs.
