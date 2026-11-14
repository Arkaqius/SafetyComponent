# Feature Specification: External Hazard Provider Plugins

**Feature Branch**: `open_spec_intruduction`

**Created**: 2026-11-12

**Status**: Draft

Selection and compatibility requirements are superseded by
[Provider Selection and Monitoring States](../002-provider-selection-states/spec.md).
The shared provider boundary remains the foundation; the superseded selection
forms do not require a compatibility implementation.

**Input**: User description: "Document selectable external-hazard providers for
installations outside Poland, shared provider results, provider-specific location
parameters, and default Open-Meteo sources. Update SYS and SSRD, retain HARA, and
record the architectural decision."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configure a provider for the installation (Priority: P1)

An operator selects an available warning provider appropriate to the installation
country, enters only that provider's required regional information, and can review
which sources and hazards will be monitored.

**Why this priority**: Regional warning services need different location data;
operators must not need Polish administrative codes for unrelated countries.

**Independent Test**: Configure a Polish installation and a non-Polish installation
using a controlled regional warning source. Check provider choices, required fields,
validation, saved values, and the monitoring summary without operating devices.

**Acceptance Scenarios**:

1. **Given** a Polish installation with IMGW selected, **When** the operator enters
   valid county codes and saves, **Then** those codes configure IMGW and the
   installation retains its shared location independently.
2. **Given** an installation outside Poland with an applicable warning source,
   **When** the operator selects it, **Then** only its regional parameters are
   required and TERYT is not required.
3. **Given** an explicitly selected provider outside its supported country or with
   missing required parameters, **When** the operator saves, **Then** the system
   identifies the invalid provider and field and leaves the saved configuration
   unchanged.
4. **Given** a bundled default unavailable in the installation country, **When**
   configuration is resolved without an explicit selection, **Then** that default
   remains inactive and is not reported as a failed installed provider.

### User Story 2 - Retain trustworthy monitoring during source failures (Priority: P1)

A resident sees which external hazards have trustworthy coverage and can distinguish
an empty official warning feed from a failed source or an unconfigured capability.

**Why this priority**: Lack of source data must never be presented as proof that an
active hazard has ended.

**Independent Test**: Supply dated controlled results, including empty feeds,
expired data, failures, and sources covering different hazards. Observe monitoring,
diagnostics, and recommendations.

**Acceptance Scenarios**:

1. **Given** a fresh, successfully validated official feed with no applicable
   warnings, **When** it is evaluated, **Then** the view states no current warnings
   within that provider's declared coverage.
2. **Given** an active hazard and a required source that times out, returns
   malformed data, or becomes stale, **When** monitoring updates, **Then** failure
   is visible and is not used as evidence to clear the active hazard.
3. **Given** independent forecast and official-warning sources, **When** one fails,
   **Then** usable evidence from the other continues to support its own covered
   hazards without representing the failed capability as healthy.
4. **Given** multiple selected sources covering the same hazard, **When** one
   reports a valid active hazard and another reports none, **Then** the active
   evidence is retained; data-based clearing requires fresh sufficient evidence
   from every selected applicable source covering that hazard.
5. **Given** no selected official-warning source, **When** the resident opens the
   external-hazard view, **Then** official warnings are shown as not configured
   even if forecast monitoring is healthy.
6. **Given** a provider covering wind only, **When** it reports no warnings,
   **Then** that result is not treated as evidence about frost, rain, or storm.

### User Story 3 - Preserve an existing installation (Priority: P1)

An operator keeps an existing configuration and existing Home Assistant consumers
while receiving the provider architecture extension.

**Why this priority**: Existing safety monitoring and household integrations must
not require a breaking migration.

**Independent Test**: Load representative existing Polish and Berlin configurations
and compare resolved source selection, stable identities, and monitoring behavior.

**Acceptance Scenarios**:

1. **Given** an existing Polish configuration with TERYT in the shared site
   section, **When** it is validated and started, **Then** IMGW receives the same
   regional selection without requiring the operator to rewrite the file.
2. **Given** both legacy and provider-specific county codes, **When** their
   normalized sets agree, **Then** configuration is accepted; **When** they
   conflict, **Then** saving and startup validation reject the conflict explicitly.
3. **Given** unchanged installation inputs, **When** the extension is activated,
   **Then** existing provider, fault, entity, topic, and raw-state identities
   remain stable.
4. **Given** existing Berlin configuration without a warning source, **When** it
   starts, **Then** the default forecast and air-quality sources remain selectable
   and no Polish county codes are required.

### User Story 4 - Introduce another supported warning provider (Priority: P2)

A maintainer adds a regional warning provider whose declared coverage, parameters,
results, and health are understood throughout the system.

**Why this priority**: A provider must integrate with diagnostics and coverage as
well as fetching warnings.

**Independent Test**: Register a controlled non-Polish warning provider and verify
configuration, complete application startup, warning presentation, failure,
recovery, and shutdown without contacting a live household.

**Acceptance Scenarios**:

1. **Given** a newly registered provider using an existing capability, **When** it
   is selected and started, **Then** its results, independent diagnostics, and
   coverage restrictions work without adding its name to household safety rules.
2. **Given** that provider's declared fields, **When** the operator configures it,
   **Then** the form and server validate the same supported parameters.
3. **Given** a stalled provider, **When** other selected providers are due,
   **Then** they continue within their configured schedules and timeout bounds.
4. **Given** a provider failure followed by a valid result, **When** health
   recovers, **Then** only its own restrictions are released; fresh hazard
   evaluation remains required before any recovery proposal becomes eligible.

### Edge Cases

- Unknown or duplicate provider identities and undeclared parameter fields are
  rejected before activation.
- Country changes preserve the draft and expose explicit incompatible selections;
  inherited inapplicable defaults remain inactive.
- Disabled providers are not polled and do not create installed-provider failures.
- Future-dated, expired, duplicate, updated, withdrawn, or unrecognized warnings
  retain explicit validity and coverage semantics.
- Unsupported warning types do not extend declared coverage or imply a safe state.
- A missing source timestamp cannot be replaced by retrieval time to invent
  freshness; cached results retain their original validity.
- A healthy empty feed proves absence only within its confirmed region, hazards,
  and current validity, and cannot cancel active evidence from another source.
- Different air-quality indices or units are not interchangeable; unsupported
  semantics are rejected rather than compared against unrelated thresholds.
- Configuration saves retain revision checks and remain separate from activation
  by an explicitly authorized application restart.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST offer bundled external-data providers by declared
  capability, supported country, and covered hazard types.
- **FR-002**: Operators MUST be able to select applicable providers and supply
  their required regional parameters without editing household safety rules.
- **FR-003**: Shared installation location MUST remain separate from
  provider-specific administrative parameters; geographic coordinates MUST come
  from Home Assistant.
- **FR-004**: The system MUST validate provider parameters using that provider's
  declared rules and reject unknown fields, unsupported explicit selections, and
  missing required values before saving or activation.
- **FR-005**: The configuration form MUST expose friendly parameter labels,
  requirements, help, and validation feedback consistent with server validation.
- **FR-006**: Open-Meteo MUST remain the default source for forecast and
  air-quality modeling; selecting a regional warning source MUST NOT replace
  forecast evidence with official-warning evidence or vice versa.
- **FR-007**: Every provider MUST supply results with stable source identity,
  covered hazard, validity, retrieval time, units where applicable, and explicit
  model-versus-official provenance. Observations MUST retain original source
  time when required by their semantics. A validated empty official feed MAY
  use retrieval time for feed freshness without inventing a source timestamp.
- **FR-008**: Providers MUST own acquisition, external-format validation,
  normalization, regional filtering, cache, and raw health; the external-hazard
  safety component MUST own household thresholds, correlation, and recommendations.
- **FR-009**: Each selected applicable provider MUST expose independent current
  health and the capability and hazards affected by its failures.
- **FR-010**: Diagnostics and coverage MUST accept a newly registered provider
  through its declared contract without fixed provider-name allocations in
  household policy.
- **FR-011**: The system MUST distinguish a healthy empty feed, unavailable data,
  unsupported coverage, and a capability with no configured source.
- **FR-012**: Stale, failed, malformed, future-inapplicable, or uncovered input MUST
  NOT provide positive clear evidence for an active hazard. Data-based clearing
  MUST require fresh sufficient results from every selected applicable source
  covering that hazard; positive closure evidence remains governed separately.
- **FR-013**: One provider's failure MUST NOT suppress independent valid hazard
  evidence or remove another provider's diagnostic restrictions.
- **FR-014**: Provider acquisition MUST remain bounded by the configured request,
  retry, response-size, and scheduling limits; a stalled provider MUST NOT block
  the other selected sources or household safety evaluation.
- **FR-015**: Existing configuration format and stable runtime identities MUST
  remain compatible. Existing shared-site TERYT codes MUST remain accepted as an
  IMGW-specific compatibility input; conflicting duplicate declarations MUST fail.
- **FR-016**: Provider selection and parameter editing MUST retain authenticated
  access, complete-document validation, revision protection, and separate
  save-versus-activation behavior.
- **FR-017**: Provider-facing operator text MUST follow the existing Polish UI
  policy; user-facing runtime additions MUST retain English, Polish, and German
  parity without translating technical identities.
- **FR-018**: Verification MUST cover a controlled additional non-Polish provider
  throughout configuration, complete startup, health, coverage, presentation,
  failure/recovery, and shutdown, as well as existing installation regressions.
- **FR-019**: The extension MUST preserve the existing hazard analysis, safety
  goals, household decision thresholds, and consent requirements for actuators.

### Key Entities *(include if feature involves data)*

- **Provider definition**: Stable identity, friendly description, capability,
  covered hazards, geographic applicability, and required parameter rules.
- **Installation location**: Shared coordinates from Home Assistant with the
  installation country and time zone.
- **Provider selection**: The installation's enablement choice and the selected
  provider's regional parameter values, distinct from packaged transport policy.
- **Provider result**: One complete source snapshot with normalized observations,
  provenance, temporal validity, and independent health.
- **Coverage contribution**: The selected provider's relationship to a particular
  capability, hazard, and household consumer; identifies the scope of unavailable
  evidence without changing the hazard's state by itself.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Polish and controlled non-Polish acceptance installations can each
  select their applicable warning source and save all required parameters with
  zero requests for unrelated countries' regional codes.
- **SC-002**: Every invalid-configuration scenario in this specification is
  rejected before saved configuration replacement or monitoring activation, with
  the affected provider or field identified.
- **SC-003**: Every failure, stale-data, unsupported-coverage, and source-conflict
  scenario preserves active evidence and produces zero hazard clears based only
  on missing or unusable data.
- **SC-004**: A controlled additional regional source completes every stage of
  configuration, startup, monitoring, diagnostic failure/recovery, and shutdown
  while the independent existing sources continue to function.
- **SC-005**: Existing Polish and Berlin acceptance configurations retain all
  stable external integration identities and require zero mandatory file rewrites.
- **SC-006**: Every supported source view distinguishes fresh warnings, no current
  warnings, unavailable evidence, and no configured official-warning source.
- **SC-007**: A stalled source does not delay another source past its configured
  polling and timeout bounds in the controlled concurrency acceptance scenarios.

## Assumptions

- HARA hazards and safety goals remain unchanged; allocation and software
  requirements are refined in SYS, SSRD, and the linked feature architecture.
- Plugins are reviewed providers bundled with the application. Runtime downloads,
  arbitrary operator-supplied code, and an installation marketplace are outside
  scope.
- This feature establishes regional-provider extensibility; choosing and adding a
  particular new live national service is a separate scope. A controlled
  non-Polish provider proves the extension contract.
- Multiple bundled sources may be selected. An active applicable source is not
  outvoted by a clear result from another source.
- One home location and one instance per stable provider identity are supported;
  multi-home and multiple accounts for the same provider are outside scope.
- Existing authentication, configuration revision protection, source format,
  lifecycle bounds, and manual-versus-confirmed actuator policy remain controlling.
- Global forecast coverage does not imply uniform resolution, identical
  air-quality models, or official-warning coverage in every country.
- Product requirements remain under `docs/`; this feature directory is the Spec
  Kit entry point and the existing architecture documents remain authoritative
  for detailed contracts.
- Controlling documents: [SYS](<../../sys/SafetyConcept - SYS.md>),
  [SSRD](<../../sys/SafetyComponent - SSRD.md>),
  [External Hazard Monitoring](<../External Hazard Monitoring - Architecture.md>),
  [Configuration Model](<../Configuration Model - Architecture.md>), and
  [ADR-0001](../../adr/0001-external-provider-plugins.md).
