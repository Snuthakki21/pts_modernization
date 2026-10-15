---
name: consult-modernization
description: Assess a modernization decision, gap, implementation option, delivery plan or cost trade-off using source-linked evidence. Use for architecture advice, SME question framing and concise decision records.
---

Read `AGENTS.md`, relevant accepted decisions and the affected contract. Use the
approved Opus 4.7 model and existing permitted tools. Do not create another agent
team or workflow engine. The foreground lead owns the resulting decision record.

1. State the required outcome, decision owner, affected programs and acceptance
   measures. Separate observed facts, assumptions and unresolved questions.
2. Inspect source/contracts and current implementations before proposing work.
   Reuse prior accepted findings only when their versions still apply.
3. Compare the simplest viable options, including reuse where compatible. Record
   behavior coverage, dependencies, implementation effort, operating cost,
   maintainability and migration/recovery implications. Use measured data; mark
   estimates with their basis and range. Do not invent ROI or token savings.
4. Recommend one option and name the trade-off. Explain why each material gap
   matters and which concrete artifact or experiment resolves it. Technical
   naming and replacement choices belong to engineering, not the SME.
5. Ask SMEs only about unresolved business meaning, intended removals or changed
   outcomes. Include exact source references and options in the current review
   workbook. Do not ask again when an applicable answer already exists.
6. Return a compact record: `decision_id`, `status`, `source_refs`, `facts`,
   `assumptions`, `options`, `recommendation`, `measures`, `owner`, `open_questions`
   and `next_action`. Add it to the process decision section or existing knowledge
   index; do not create a report per rule or duplicate the technical contract.

Do not turn a recommendation into approved business behavior. If evidence is
missing, state the conditional conclusion and continue independent work. For
claims of improved model quality, define a repeatable evaluation against labeled
source tasks and measured defects; prompts cannot guarantee another model's ability.
