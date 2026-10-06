# Workbench repository instructions

Read [AGENTS.md](../AGENTS.md) for repository boundaries. For modernization
execution, use the single shared
[prompts/START_MODERNIZATION.md](../prompts/START_MODERNIZATION.md). Claude Code's
[CLAUDE.md](../CLAUDE.md) references the same workflow. Preserve those links and
avoid a competing conversion engine or duplicate operational prompt.

The Python service is `workbench.coordinator.Coordinator`; the UI and
`python -m workbench.runner` share its ledger, one SME quota and artifact gates.
Read `START_HERE.md` for environment setup. Run meaningful regression tests with
`python -m unittest discover -s tests`. Engine changes need real tests and
adversarial review before any completion claim.

Preserve [docs/TECHNICAL_REFERENCE.md](../docs/TECHNICAL_REFERENCE.md). Validate with
`python -m workbench.layout --workspace WORKSPACE` before and after work.
Process output stays under `processes/PROCESS_ID/{input,analysis,review,synthetic,target,reports,tests}`;
shared target versions and canonical approved knowledge have their documented
locations. Keep scratch under ignored `.implementation/tmp/`; root directory
names are explicitly allowlisted. Do not create a Markdown file for every rule,
overwrite source exports/frozen evidence, or publish private inputs/secrets.

Mainframe access is always read-only. Every selected source file and line needs
coverage disposition and evidence/reason; platform behavior needs a verified
replacement. Source-derived tests are separate from observed mainframe parity.
Deliver the one SME packet and wait for the actual reviewer return. Never fill
SME answers, infer approval from silence, bypass blockers or claim unsupported
parity, production readiness or zero bugs.
