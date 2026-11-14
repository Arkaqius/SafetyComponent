# Contract: Applied Monitoring and Presentation

## Authoritative applied selection

SafetyFunctions publishes sensor.external_source_selection with the snapshot in
[data-model.md](../data-model.md) after validation/MQTT setup and before polling.
It is published even when C-EXT or every category is disabled. Its entity state is
ready; HA availability remains authoritative for process connection.

C-EXT provider diagnostics, aggregate and separate test preview attach the same
runtime_id. A browser considers evidence current only for a matching applied
generation and source, usable timestamps and a connected runtime. Missing,
unsupported, unavailable or stale selection snapshots yield unknown; absence is
never a disabled proof.

Never substitute GET /api/config, unsaved browser state, inherited defaults,
enabled_providers or a retained provider entity for applied selection.

## Presentation precedence

| Condition | Category appearance | Real current count |
| --- | --- | --- |
| C-EXT explicitly off in applied snapshot | Muted grey, “Wyłączone” with component explanation | — |
| Category provider is null | Muted grey, “Wyłączone” | — |
| Applied metadata missing/invalid/disconnected | Neutral uncertain, “Brak aktualnego stanu konfiguracji” | — |
| Selected synthetic provider | “Źródło testowe — dane syntetyczne”; separate preview | — |
| Selected live source, no same-generation evidence | “Oczekiwanie na dane” | — |
| Selected source lacks this hazard | “Brak obsługi tego zagrożenia” | — |
| Live source failed/malformed | Failure and “Brak wiarygodnych danych” | — |
| Live source stale | Stale warning with separately labelled retained evidence | — |
| Fresh complete healthy empty official feed | “Brak aktualnych ostrzeżeń” scoped to coverage | 0 |
| Fresh applicable official warnings | Current warnings and actual provider attribution | Count |
| Fresh model evidence | Available model values; independently derived real hazard state | Evaluated value/count only |

A valid target source always explicitly chooses null or an ID. The existing
not_configured coverage reason still describes missing applicable live coverage,
including synthetic-only categories; selection_state distinguishes deliberate
disabled from test-only/unknown. Backend real coverage_details never marks a
synthetic source available or no_current_warnings.

Disabled applies to monitoring status and new detection counters. It never hides
a previously active real H fault, marks it cleared, suppresses real active-hazard
warnings or overwrites retained evidence. Real positive clear and physical
opening-closure rules remain in force.

Apply muted/unknown semantics to the page headline, healthy-source summary,
detection counters, category sections, provider cards and hazard coverage details.
A clear raw aggregate with all categories disabled/test-only must not yield a
green “monitoring safe” claim. Independently enabled live categories keep their
own state. On disconnect the hooks invalidate all current category/preview claims.

## Neutral names and branding

Polish category labels: Pogoda, Oficjalne ostrzeżenia pogodowe, Jakość powietrza.
Keep actual provider names in choices, source attribution and warning details.
Rename generic imgw-* CSS classes and provider-name fallback branches to neutral
warning/category naming. Use catalogue/runtime display metadata, not a new hardcoded
provider-name map. No rename of healthy real provider IDs/topics is necessary.

Disabled text and icons must be accessible independently of grey. Keyboard focus,
field labels and layout work at 390 px and desktop widths without horizontal
overflow. EN/PL/DE runtime labels keep equal keys/format placeholders; the operator
guide and UI stay Polish.

### Restart retention

Checkpoint active real opening/hazard assertions in the existing SQLite store as
specified in [data-model.md](../data-model.md#realassertioncheckpoint). Restore
before publishing initial FaultManager/MQTT state. New null selections, C-EXT off
or a synthetic replacement must not publish HEAL/inactive for a retained assertion.
The page shows it separately from disabled monitoring, as retained unevaluable
real danger. No prior notification, proposal, command or qualification timer is
replayed. Missing/corrupt checkpoint or no matching usable retained record with
active journal evidence keeps the fault active/UNEVALUABLE and coverage unknown,
not healthy clear. Storage failures and overflow are explicit, not silent drops;
a failed clear write withholds the clear, while a failed assertion write retains
asserted danger in memory under observable persistence failure.

The external fault attributes retained_assertions and retained_hazard_unknown
are the authoritative retained-danger presentation, independent of provider
diagnostics and the disabled/test category state. Same-start applied selection
still controls current monitoring, but must not hide this older real danger.
Do not flatten retained real assertions into synthetic warnings or current
provider observation counts.

The global safety_coverage_state attributes retained_external_assertion_count,
retained_external_assertions (maximum 32) and retained_hazard_unknown explain
unresolved retained danger. Their wrapper changes FULL/PARTIAL to UNKNOWN without
overriding DEGRADED. Recovery restore excludes external exposure proposal IDs
(checkpoint plus configured exposure symptoms), so startup cannot restore an old
recommendation, consent or execution merely from a retained assertion.

## Acceptance boundary

Observe the applied snapshot after save without restart, after restart, with the
whole component off, all categories null, and old healthy diagnostics retained.
Assert no disabled count falls back to zero. Test unavailable/unknown, unsupported
hazards and synthetic preview separately from real active warning retention.
