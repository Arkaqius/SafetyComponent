# ADR-0001: Bundled external-hazard provider plugins

**Date:** 2026-11-12

**Status:** Accepted design decision

## Context

External-hazard monitoring needs forecast models, official regional warnings,
and outdoor-air-quality evidence. Providers differ in payloads, location codes,
time semantics, coverage, and failure modes. IMGW's TERYT selection is specific
to Poland; it is not a universal installation-location model. Global forecast
availability does not supply official warnings for every country.

The existing provider registry and normalized results provide a reusable
boundary. The system needs that boundary throughout configuration, startup,
diagnostics, and coverage, rather than only at network acquisition.

## Decision

- Use reviewed provider adapters bundled with the application and selected in
  installation configuration. Do not introduce runtime package installation.
- Keep Open-Meteo weather and air quality as default model sources behind the
  same internal contract. Select official-warning providers independently.
- Each plugin declares its stable ID, capability, covered hazards, applicable
  countries, runtime schema, editable-parameter schema, and friendly metadata.
  It owns acquisition, provider validation, normalization, regional filtering,
  cache, and raw health. C-EXT owns household thresholds and safety decisions.
- Keep coordinates from Home Assistant and shared country/timezone separate
  from `user_config.providers.<ProviderId>.parameters`. Place canonical IMGW
  codes under `providers.ImgwWarningsApiComponent.parameters.teryt_codes`.
- Preserve source model version `2` and `installation.site.teryt_codes` as an
  IMGW compatibility input. Accept both forms only when their normalized code
  sets agree; reject conflicts without rewriting the saved source.
- Derive configuration fields, diagnostics, and degradation dependencies from
  provider declarations and installed consumers, without fixed provider-name
  lists. Preserve existing provider, fault, topic, entity, and raw-state IDs.
- Retain valid active evidence from any applicable source. A complete healthy
  empty feed applies only to its declared coverage. Data-based clearing requires
  fresh sufficient evidence from all selected applicable providers covering the
  hazard; unavailable or uncovered input is not positive clear evidence.

## Alternatives considered

- **Only regional services use adapters:** makes the default model provider a
  special path with duplicated lifecycle and error handling. A common internal
  contract allows a default user experience without that coupling.
- **Add every regional field to the shared site:** spreads provider-specific
  validation through the compiler and UI. Provider-owned parameters localize it.
- **Keep provider-name tables in diagnostics:** allows registration to succeed
  while full startup or coverage rejects a new adapter. Registry-derived
  allocation makes the extension contract cover the whole application.
- **Load arbitrary third-party packages at runtime:** adds an installation and
  executable-code lifecycle outside the need for configurable bundled sources.

## Consequences

New conforming providers can reuse household policy, diagnostics, and the editor.
They still require reviewed schemas, approved transport configuration, explicit
coverage, localization, and contract/integration evidence. Different warning
levels and air-quality indices must retain their semantics during normalization.

The change refines SYS allocation and SSRD software contracts without changing
HARA hazards, safety goals, thresholds, or actuator consent. Acceptance includes
a controlled non-Polish provider through complete startup, failure/recovery,
coverage, presentation, and shutdown; it does not certify an additional live
national service. Saving configuration remains separate from authorized restart.

## References

- [Feature specification](../features/001-external-provider-plugins/spec.md)
- [SYS external-hazard requirements, section 8.3.6](<../sys/SafetyConcept - SYS.md>)
- [SSRD external-hazard requirements](<../sys/SafetyComponent - SSRD.md#48-external-hazard-monitoring>)
- [External Hazard Monitoring architecture](<../features/External Hazard Monitoring - Architecture.md>)
- [Configuration Model architecture](<../features/Configuration Model - Architecture.md>)
