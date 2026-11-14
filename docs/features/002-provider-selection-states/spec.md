# Feature Specification: Provider Selection and Monitoring States

**Feature Branch**: `open_spec_intruduction`

**Created**: 2026-11-13

**Status**: Draft

**Input**: User description: "Use provider-neutral wording in configuration and
external hazards. Select a plugin or disabled instead of enabled/default/disabled;
show fields for the chosen plugin. Grey out disabled monitoring rather than
showing green zero detections. Add a dummy German plugin without a live service
to exercise our part of the system. Backwards compatibility is not required;
use one target model without legacy aliases, inheritance controls or migration
and reconciliation flows."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Choose a source and its parameters (Priority: P1)

An operator selects a named provider or "Wyłączone" for an external-data
category. Only the selected provider's installation fields appear. Shared
location settings remain available independently of provider-specific fields.

**Why this priority**: The operator chooses the data source directly and does
not need to understand inheritance or enter another provider's regional codes.

**Independent Test**: Open Polish and German installation drafts, choose an
applicable provider, change its fields, disable it, save and reopen. Compare the
selected source, visible fields, retained draft values and effective monitoring.

**Acceptance Scenarios**:

1. **Given** a Polish installation, **When** the operator opens source selection,
   **Then** the category uses a neutral name and offers applicable named providers
   and "Wyłączone", without enabled or default options.
2. **Given** IMGW is selected, **When** its settings are shown, **Then** its own
   TERYT fields are visible; the generic category is not named IMGW.
3. **Given** a German installation, **When** the German test provider is selected,
   **Then** its declared fields appear and no Polish TERYT field is requested.
4. **Given** a configured provider, **When** the operator selects "Wyłączone",
   **Then** its parameter fields are hidden and values are retained for reselection
   without being used for monitoring while disabled.
5. **Given** a valid saved choice and parameter values, **When** configuration is
   reopened, **Then** the same effective choice and values are displayed.
6. **Given** a saved configuration in the target model, **When** the form is opened
   without an edit, **Then** the saved named provider or disabled choice is shown
   without creating a dirty draft.
7. **Given** unsupported, unknown or incompatible saved selections, **When** the
   form opens, **Then** they remain visible with a corrective explanation rather
   than silently becoming disabled or another source.
8. **Given** an unsaved source change, **When** the monitoring page is opened,
   **Then** its status still describes the applied monitoring configuration;
   saving and applying a change remain distinct operations.

---

### User Story 2 - Recognize disabled and unavailable monitoring (Priority: P1)

An operator reading External Hazards can distinguish disabled monitoring from
a healthy source reporting no current warnings, and from an enabled source
whose evidence is unavailable.

**Why this priority**: A green zero can incorrectly suggest monitoring is working
when the operator disabled its source.

**Independent Test**: Present disabled, unconfigured, unsupported, waiting,
failed, healthy-empty and active-warning cases. Verify text, appearance, counts
and retained evidence on desktop and mobile without operating household devices.

**Acceptance Scenarios**:

1. **Given** official-warning monitoring is disabled in the applied configuration,
   **When** External Hazards is opened, **Then** its section remains visible in a
   grey/muted state labelled "Wyłączone", with no green healthy indicator or
   numerical zero that suggests an evaluated absence of warnings.
2. **Given** the installation has no applicable configured warning provider,
   **When** the section is opened, **Then** it is muted and explains the missing
   configured source rather than claiming no warnings.
3. **Given** an enabled healthy source returns a complete empty warning result,
   **When** its section is shown, **Then** zero current warnings is permitted and
   is explicitly scoped to that source's configured coverage.
4. **Given** an enabled source is waiting, stale, failed or malformed, **When** the
   section is shown, **Then** its uncertainty or failure is explicit and it does
   not appear as disabled or as a healthy zero.
5. **Given** official warnings are disabled but weather and air-quality monitoring
   remain enabled, **When** External Hazards is shown, **Then** the official
   section is muted and the independently enabled sources keep their own states.
6. **Given** an active warning was previously received, **When** its provider is
   disabled or unavailable, **Then** historical/retained evidence is clearly
   separated from current monitoring and the change does not manufacture a
   positive safety clear.
7. **Given** a non-IMGW source supplies warnings, **When** configuration, summaries,
   empty states and warning details are displayed, **Then** generic text remains
   provider-neutral and the source's own name identifies its provenance.

---

### User Story 3 - Exercise a German test source (Priority: P2)

A tester selects a clearly marked German dummy provider and exercises source
selection, parameters and warning presentations without relying on a real
German warning service.

**Why this priority**: A second selectable provider demonstrates the complete
operator experience and exposes country- or provider-specific assumptions.

**Independent Test**: In a German acceptance installation, select the test source,
enter its declared regional setting and exercise repeatable no-warning, active
warning, unavailable and stale scenarios. Verify isolation from household actions
and from real monitoring evidence.

**Acceptance Scenarios**:

1. **Given** a German installation, **When** its warning-source choices are opened,
   **Then** a German provider explicitly labelled "testowe" is selectable and its
   description explains that it supplies synthetic data.
2. **Given** the test provider is selected with valid parameters, **When** each
   test scenario is chosen and applied, **Then** the resulting warning, empty,
   unavailable or stale presentation is repeatable and visibly marked as test data.
3. **Given** the source is supplying test data, **When** configuration and
   monitoring are exercised, **Then** it makes no request to a real warning
   service and requires no service credential.
4. **Given** test warnings or empty test results, **When** household safety
   decisions are evaluated, **Then** they cannot assert or clear real household
   hazard conditions, satisfy real monitoring coverage, issue real alarm
   notifications, or create or execute actuator commands.
5. **Given** a normal installation with no explicit test selection, **When** it
   starts or changes country, **Then** the test source never activates implicitly.
6. **Given** a non-German installation, **When** available choices are shown,
   **Then** the German test provider is not offered as an applicable live source;
   an incompatible existing explicit selection remains visible for correction.

---

### Edge Cases

- A selected provider lacks required parameters or has malformed supplied values:
  saving identifies the field; disabling allows incomplete required values but
  does not silently accept malformed supplied values.
- A country change makes the current provider incompatible: show the conflict,
  retain the draft and require a deliberate compatible selection or disabling.
- Switching between providers preserves each provider's draft values and shows
  only the currently selected provider's fields.
- A category specifies more than one selected provider: reject the invalid
  configuration and identify the category; there is no reconciliation flow.
- An input uses an obsolete configuration shape: reject it with an actionable
  validation message rather than interpreting aliases or converting it implicitly.
- Disabled sources retain old diagnostics or warning counts: retained data cannot
  override the applied disabled status or appear as current zero-warning evidence.
- All sources are disabled: category and overall coverage must not imply healthy
  monitoring; an independent active hazard is not silently cleared.
- Unknown applied configuration or missing selection metadata: show uncertainty;
  do not infer disabled solely from missing entities.
- Disabling the whole external-hazard component mutes its monitoring sections
  without changing the states of unrelated safety components.
- A stale revision rejects a save: the draft and its provider-specific values are
  retained for correction, with no misleading change to applied monitoring.
- Test and real providers coexist in different categories: synthetic results stay
  visibly separate and cannot improve real coverage or remove real restrictions.
- Grey is not the only status cue: text and accessible labels convey disabled
  status to keyboard and screen-reader users.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Generic external-source headings, descriptions, help, counters and
  empty states in configuration and External Hazards MUST use capability/category
  language independent of IMGW or another provider. Provider names MUST remain
  visible where they identify a selected source or warning provenance.
- **FR-002**: Each editable external-data category MUST offer named applicable
  provider choices and "Wyłączone". It MUST NOT expose "Włączone" or "Domyślnie"
  as source-selection choices. Global model sources MUST remain independently
  configurable from official-warning sources.
- **FR-003**: The form MUST reveal only the selected provider's declared
  installation parameters and validation messages. Shared home location MUST
  remain independent; unrelated providers' regional codes MUST NOT be required.
- **FR-004**: Switching or disabling a source MUST retain provider-specific draft
  values for reselection, while preventing inactive values from enabling that
  source. Requiredness MUST apply to the selected active provider.
- **FR-005**: Each category MUST have one explicit selected provider or an explicit
  disabled choice in the target configuration model. Opening valid saved settings
  MUST NOT dirty the draft. Invalid selections MUST produce an actionable error;
  the form MUST NOT infer a replacement source.
- **FR-006**: Saving and applying monitoring changes MUST retain existing
  authorization, revision protection and separate restart/application behavior.
  External Hazards MUST describe applied monitoring rather than an unsaved draft.
- **FR-007**: Disabled external monitoring MUST remain visible with muted grey
  styling and explicit disabled text. Its warning/detection summary MUST use
  disabled/not-evaluated text or a nonnumeric placeholder instead of green health
  or zero detections implying monitoring.
- **FR-008**: Disabled, unconfigured, unsupported, awaiting evidence, unavailable,
  stale, healthy-empty and active-warning meanings MUST remain distinguishable.
  Missing or unknown configuration MUST NOT be silently interpreted as disabled.
- **FR-009**: A healthy zero-warning presentation MUST require an enabled provider
  and fresh, complete, applicable evidence, scoped to its supported hazards.
  Disabling one category MUST NOT disable independent model monitoring or change
  another category's evidence.
- **FR-010**: Disabling, missing input, failed data or a display-state change MUST
  NOT count as positive clear evidence for an active household safety condition.
  Retained warnings MUST identify their historical or inactive-source status.
- **FR-011**: A selectable German dummy warning provider MUST be available for
  explicit testing in German installations, have its own declared regional
  parameter, and be conspicuously identified as synthetic in selection, help,
  monitoring status, counts and warning details.
- **FR-012**: The German dummy provider MUST support repeatable healthy-empty,
  active-warning, unavailable and stale test scenarios without a live external
  warning service or credentials. Its declared hazard scope MUST be explicit;
  lack of support for other hazards MUST remain visible.
- **FR-013**: Test-provider activation MUST require deliberate selection and MUST
  NOT be inherited as a default or substitute for a missing real provider.
  Synthetic results MUST remain isolated from real hazard state, real monitoring
  coverage, real alarm notifications and household actuator proposals/execution.
- **FR-014**: Configuration and provider selection MUST use one documented target
  model. Superseded selection forms, legacy parameter aliases, compatibility
  fallbacks and migration/reconciliation flows MUST NOT be retained for this
  feature. Required contract changes MUST be synchronized across documentation,
  configuration, implementation and tests. Safety consent rules MUST remain in force.
- **FR-015**: Selection, provider-specific fields, disabled styling and test-data
  markers MUST work on desktop/mobile and with keyboard/screen-reader interaction.
  Operator UI wording MUST be Polish; affected runtime labels MUST retain
  English/Polish/German parity.
- **FR-016**: Automated acceptance MUST exercise Polish and German selection,
  hidden/revealed parameters, save/reload of the target model, all monitoring display
  states, retained evidence and synthetic-source isolation without household
  actuator calls.

### Key Entities *(include if feature involves data)*

- **External-data category**: A source-selection purpose, such as official weather
  warnings, weather modelling or outdoor air quality.
- **Provider choice**: An applicable named source or explicit disabled choice,
  with its effective applied selection distinguished from an editable draft.
- **Provider parameters**: Installation-specific values belonging to one provider,
  retained independently of which provider is currently selected.
- **Monitoring presentation**: The category's enabled/disabled and evidence state,
  supported scope, current warning summary and separately retained history.
- **German test provider**: An explicitly selected synthetic source with a declared
  region, hazard scope and deterministic scenario; its evidence is not real safety
  evidence.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In Polish and German acceptance journeys, operators can choose a
  source or disable a category and save valid settings in no more than three
  selection steps, excluding typing parameters.
- **SC-002**: Across every supported provider-switch scenario, 100% of visible
  provider-specific input fields belong to the selected provider, and reselection
  restores previously entered draft values.
- **SC-003**: In every disabled-monitoring acceptance case, there are zero green
  healthy indicators or numerical detection zeros implying active monitoring in
  the disabled scope; explicit disabled text is visible on desktop and mobile.
- **SC-004**: Every state in FR-008 has an unambiguous operator-facing explanation;
  only fresh complete healthy empty real evidence yields a real no-warning result.
- **SC-005**: The four German dummy scenarios are repeatable without external
  warning-service access, with visible test markers on every affected source and
  warning view and zero effects on real safety state or household actions.
- **SC-006**: Every supported category has exactly one explicit provider-or-disabled
  choice; all target-model save/reload cases preserve that choice and its parameters.
  Acceptance requires zero legacy alias, inheritance-selection or migration flows.
- **SC-007**: All generic source/category labels in the two affected screens are
  provider-neutral; any provider brand shown identifies the actual source.

## Assumptions

- Product documentation remains under `docs/` as required by the repository
  constitution and the user's established documentation location. This feature is
  `docs/features/002-provider-selection-states/`; the existing 001 feature remains
  available as the provider-contract foundation.
- "GER" means Germany, represented by the installation's existing country code
  `DE`; no alternative country-code convention is introduced.
- A selector chooses one provider per data category. Backwards compatibility is
  explicitly waived by the user for this development feature: configuration
  contracts may change and older installation files may require manual replacement.
  No compatibility layer, automatic migration or old multi-source reconciliation
  is required. Internal provider support remains extensible.
- This feature supersedes conflicting compatibility requirements in feature 001
  for the affected selection and parameter model. Planning shall update the
  controlling architecture and requirements consistently instead of carrying
  both models forward. This is an explicit user-authorized contract change under
  the constitution; safety evaluation and consent requirements still apply.
- IMGW remains a valid Polish provider name. The request removes its use as the
  generic name of a category, not its attribution. Technical identifiers need only
  change where required by the target contract, with coordinated consumer updates.
- Open-Meteo retains its global model roles. A German real national warning
  integration, provider marketplace and live service connection are outside scope.
- The dummy is available through the operator flow, beyond an internal test-only
  fixture. It is off by default, uses explicit synthetic scenarios and is isolated
  from real safety decisions; broader hazard coverage is unnecessary for proving
  the second-provider experience.
- HARA hazards and safety goals remain unchanged. Planning shall map this feature
  to affected SYS/SSRD allocations and architecture before implementation,
  particularly existing SWR-EXT-024 through SWR-EXT-027.
- This specification defines intended behavior only. It changes no runtime,
  installation file or deployed instance and authorizes no live action.
- Controlling context: [provider foundation](../001-external-provider-plugins/spec.md),
  [Configuration Model](<../Configuration Model - Architecture.md>),
  [External Hazard Monitoring](<../External Hazard Monitoring - Architecture.md>),
  [SYS](<../../sys/SafetyConcept - SYS.md>),
  [SSRD](<../../sys/SafetyComponent - SSRD.md>), and
  [constitution](../../../.specify/memory/constitution.md).
