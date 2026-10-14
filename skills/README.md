# Skills

Skills are reusable instructions for specialized AI capabilities.

Each skill should live in its own directory and use `SKILL.md`.

Example:

```text
skills/
├── commerce-analytics/
│   └── SKILL.md
├── payment-analytics/
│   └── SKILL.md
├── revenue-recovery/
│   └── SKILL.md
├── data-ingestion/
│   └── SKILL.md
└── tenant-security/
    └── SKILL.md
```

Skills should describe:

- Purpose
- Inputs
- Allowed tools
- Workflow
- Output expectations
- Restrictions
- Failure handling

`SKILL.md` is recommended over a custom `agentskill.mf` extension unless a specific agent framework requires that format.
