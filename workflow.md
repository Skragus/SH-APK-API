# Cursor AI Workflow Rules

This project follows a structured AI-assisted development workflow. **Always follow these rules:**

## Core Principles

1. **Follow the workflow documentation** - Read and follow the guidelines in:
   - `docs/ai/CONSTRAINTS.md` - Development constraints and boundaries
   - `docs/ai/WORKFLOW.md` - Default development workflow
   - `docs/ai/DEFINITION_OF_DONE.md` - Completion checklist

2. **Use task files** - When starting any work:
   - Create or reference `tasks/TASK-<slug>.md` as the source of truth
   - Follow the task structure: Goal, Non-goals, Blast radius, Acceptance checks, Test plan

3. **Small, verified changes**:
   - One checkpoint per message/change
   - Run tests/build after each change
   - Commit checkpoints frequently with clear messages
   - Never stack unverified changes

4. **Scope control**:
   - Only modify files explicitly mentioned or directly required
   - No drive-by edits outside requested files
   - No new dependencies unless requested
   - Prefer smallest change that works

5. **Stop and ask**:
   - If requirements are ambiguous
   - If you're unsure about a decision
   - If something conflicts with constraints
   - Don't make assumptions

## Default Workflow

When starting any task:

1. Reference or create task file in `tasks/TASK-<slug>.md`
2. Write a step-by-step plan (max 5-8 steps) with verification per step
3. Implement one step at a time
4. Verify after each step (tests, lint, build, or manual check)
5. Commit checkpoint: `TASK: <slug> step <N> - <what changed>`
6. Repeat until all acceptance checks are met

## Code Style

- Follow existing code patterns in the repository
- Use minimal header formatting
- Concise comments, simpler variable names
- Casual or removed summary sections
- Don't deviate from existing code style

## Before Declaring Done

Check `docs/ai/DEFINITION_OF_DONE.md`:
- [ ] Tests pass
- [ ] Lint passes
- [ ] Acceptance checks met
- [ ] No unrelated diffs
- [ ] Code is readable
- [ ] Build succeeds

## When to Escalate

Stop and ask for human decision on:
- Architectural changes (new modules, data models, major flows)
- Auth/security/permissions/payment logic
- Ambiguous requirements
- Proposed new dependencies or major refactors
- Any change you can't explain clearly

Remember: You're orchestrating a semi-competent gremlin with hands. Give it tight scope, explicit done conditions, short checkpoints, validation every step, and small commits.