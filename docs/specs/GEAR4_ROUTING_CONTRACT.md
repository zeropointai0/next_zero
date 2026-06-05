# ZeroPointAI — Gear 4 Routing Contract v1.0

## Purpose

This document defines how Gear 4 chooses the best solution path for a user goal.

Gear 4 should not immediately execute every request as a task.

Gear 4 must first ask:

> What is the best long-term solution?

## Pipeline

```text
goal
  ↓
zero_decomposer.py
  ↓
zero_specialization_engine.py
  ↓
Recommendation(path=...)
  ↓
zero_gear4.py routes execution
```

## Recommendation Object

```python
Recommendation(
    path: DIRECT | FUNCTION | TASK | ENTITY,
    confidence: float,
    reason: str,
    next_action: str,
    ask_frank: bool
)
```

## Paths

### DIRECT

Zero answers directly in chat.

Use when:

- The answer is simple.
- The task is immediate.
- No long-term memory or specialization is needed.
- No new function or module is needed.
- No multi-step mission is needed.

Examples:

- "What does address already in use mean?"
- "Where is the zip file?"
- "Explain this traceback."

### FUNCTION

Zero should create or improve a reusable function/module.

Use when:

- The problem is recurring.
- The solution is technical and bounded.
- Code is a better answer than an Entity.
- No specialized persona or long-term apprenticeship is needed.

Examples:

- Backup script.
- Import scanner.
- Config validator.
- Highscore export module.

### TASK

Gear 4 should run a structured mission.

Use when:

- The goal requires several steps.
- The work is finite.
- It may require research or analysis.
- It should produce a result and then end.
- It does not justify a long-term specialist.

Examples:

- Analyze a set of files.
- Research a pinball repair issue.
- Compare three versions of Gear 4.

### ENTITY

Zero should recommend or create a Draft Entity.

Use when:

- The domain recurs often.
- It requires long-term learning.
- It benefits from specialized memory.
- It needs a constitution, style, study plan or tools.
- It gets better over weeks/months.

Examples:

- Minna.
- Master Trader Assistant.
- Pinball Social Entity.

Important:

ENTITY never means "launch an active autonomous agent immediately."

ENTITY means:

```text
Create Draft Entity
or
Start Entity Creation Wizard
```

## Confidence Rules

```python
confidence >= 0.90:
    proceed automatically
    if ENTITY: create DRAFT entity only

0.65 <= confidence < 0.90:
    propose recommendation and ask Frank

confidence < 0.65:
    ask Frank before doing anything important
```

## Philosophy

The old Gear 4 question was:

> How do I solve this?

The new Gear 4 question is:

> Should I solve this directly, automate it, run a mission, or grow a specialist?

This is the difference between a task-runner and a self-specializing system.

## Design Principle

Gear 4 should be a conductor, not the whole orchestra.

The intelligence should be distributed:

```text
zero_decomposer.py              understands the goal
zero_specialization_engine.py   chooses path
zero_task.py                    manages mission state
zero_entity_wizard.py           designs entities with Frank
zero_entity_manager.py          manages entity lifecycle
zero_gear4.py                   orchestrates
```

## Entity Lifecycle

Official lifecycle:

```text
DRAFT
APPRENTICE
ACTIVE
MASTER
DORMANT
RETIRED
```

A new Entity always begins as DRAFT.

No Entity becomes ACTIVE without earned trust.

## Why this spec matters

Code shows how the engine behaves.

This spec explains why it behaves that way.

Human developers need the spec.

Other AIs also benefit from the spec because it gives architectural intent, not just implementation details.
