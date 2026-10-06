# Claude Code entrypoint

Read [AGENTS.md](AGENTS.md) for repository boundaries, then execute the single
shared [prompts/START_MODERNIZATION.md](prompts/START_MODERNIZATION.md) workflow.
Keep these references intact when organizing future work. Do not copy the
workflow into a competing prompt or create another modernization engine. GitHub
Copilot's [.github/copilot-instructions.md](.github/copilot-instructions.md) also
references that same prompt.

Use `python -m workbench.runner`, backed by the existing Coordinator, and validate
placement with `python -m workbench.layout --workspace WORKSPACE`. The folder
contract is [docs/TECHNICAL_REFERENCE.md](docs/TECHNICAL_REFERENCE.md). Source exports
are immutable, mainframe operations are read-only, the one SME review is human,
and completion requires real verification, source coverage accountability and
adversarial review. Never manufacture approval or an unsupported success claim.
