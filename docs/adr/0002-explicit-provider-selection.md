# ADR-0002: Explicit provider selection and isolated synthetic previews

**Date:** 2026-11-13

**Status:** Accepted design decision

## Context

An inherited enablement switch does not answer which source an operator chose.
Disabled-source diagnostics can leave a misleading green zero-warning view.
A second selectable source is needed to exercise the operator experience without
connecting a German national warning service. The user explicitly waived
backwards compatibility for the affected development configuration contract.

## Decision

- Use one required `external_sources` category map with a provider ID or null per
  capability, plus one `provider_parameters` map. Keep source version 2 while
  accepting only this target shape. Remove inherited provider enablement, old
  selection forms, TERYT aliases and reconciliation/migration flows.
- Retain normal provider-owned validation and separate system transport policy.
  Preserve unrelated asset precedence, revision protection and restart consent.
- Publish applied selections independently of C-EXT activation, with per-start
  runtime identity. Monitoring consumes applied state, not saved or draft state.
  Disabled monitoring is muted and unevaluated; stale retained data cannot make it
  a healthy zero. Retained real active hazards remain visible and protected.
- Checkpoint active real C-EXT assertions in the existing SQLite store and restore
  them before initial fault publication. The evidence journal alone is not a full
  contributor snapshot. Restored danger is unevaluable until positively cleared;
  timers, notifications, proposals and commands are not replayed.
- Bundle a clearly synthetic German wind-warning provider with no network
  transport. Trusted declarations route its results to a separate preview event
  and entity. Synthetic data cannot affect real H/D state, coverage, notifications,
  advice inhibition, recovery proposals or household actions.
- Use neutral category text and actual provider names only for provenance. Keep
  global models as explicit independently selectable sources.

## Alternatives considered

- A simplified UI over legacy bindings keeps the rejected complexity in source,
  compiler and tests.
- Inferring disabled from absent entities confuses selection with booting,
  disconnection or missing metadata.
- A normal live dummy with a UI badge can change real safety state before display.
- A separate application/runtime duplicates scheduling; a separate trusted event
  and preview boundary isolates synthetic results within the current runtime.

## Consequences

Older affected source files require manual replacement; no compatibility converter
is provided. Documentation, schemas, examples, compiler, API, UI and tests must
change together. All existing safety consent and positive-clear rules remain in
force; HARA hazards and goals are unchanged. This decision supersedes ADR-0001's
compatibility and inherited-selection clauses only; provider isolation and
household-policy ownership remain controlling.

## References

- [Feature specification](../features/002-provider-selection-states/spec.md)
- [Implementation plan](../features/002-provider-selection-states/plan.md)
- [Source selection contract](../features/002-provider-selection-states/contracts/source-selection.md)
- [Monitoring presentation contract](../features/002-provider-selection-states/contracts/monitoring-presentation.md)
- [Synthetic provider contract](../features/002-provider-selection-states/contracts/synthetic-provider.md)
- [ADR-0001](0001-external-provider-plugins.md)
