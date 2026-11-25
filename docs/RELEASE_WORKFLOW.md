# SafetyComponent release workflow

Use this workflow for a candidate that will be verified on Home Assistant.
The [feature workflow](../.specify/workflows/speckit/workflow.yml) validates
the StrictDoc baseline and Beads graph before implementation. The release
workflow uses executable results to decide whether a candidate can advance.
Publishing an image supplies a candidate for this workflow.
The [requirements CI workflow](../.github/workflows/requirements-quality.yml)
checks feature requirements and architecture. The
[application CI workflow](../.github/workflows/safety-component-app.yml)
checks the application and builds its image.

## Requirements and verification

Trace stakeholder needs and applicable HARA safety goals to system requirements,
then to allocated software requirements. Use the existing UIDs when adopting
legacy requirements. The StrictDoc requirement kinds are `FUNCTIONAL`,
`QUALITY` and `CONSTRAINT`. Record architecture decisions separately and
link their governing requirements. Specify measurable limits and the conditions
under which they apply. Use the [StrictDoc authoring procedure](../CONTRIBUTING.md#validating-requirements-and-architecture).

Use static analysis for rules it can prove, unit tests for isolated software
behaviour, and software integration tests at component boundaries. Use system
tests for behaviour observable across the deployed application, HA and its
interfaces. Exercise timing, failure and recovery on an authorized isolated
target when the requirement depends on that environment. Base acceptance on the
approved requirement and interface and record the expected result before
examining the implementation. Use an operator scenario for stakeholder
validation when the change affects a household workflow.

## Gate order

| Gate | Required result | Role |
| --- | --- | --- |
| Candidate qualification | The applicable StrictDoc, backend and frontend CI checks pass for the candidate commit. Record the build version, image digest, target alias and configuration revision or redacted fingerprint. | Irena collects the references. Jurand maintains the executable checks. |
| Isolated-target authorization and preflight | An authorized person approves the exact candidate, target and actions. Verify target compatibility, configuration validation and a usable backup and recovery path before installation. | Irena records authorization. Jurek verifies target and build. Basia checks the restoration baseline. |
| System verification | Deploy and verify the candidate on the authorized target. Run applicable smoke, end-to-end, degradation and recovery scenarios. Record results against their requirement UIDs. Include operator evidence when required by the change. | Jurek records integration evidence, Basia records recovery evidence, and Hania records simulated operator acceptance. Kazek independently reviews safety-contract evidence. |
| Household promotion | Required evidence passes for the same image digest. Review differences between test and household configurations and resolve their impact on the evidence. An authorized person approves the household target and actions. Verify the household configuration and recovery point before installation. | Irena presents the evidence for human decision. |
| Post-deploy verification | Observe the running version, readiness and monitoring continuity using the authorized smoke checks. On failure, stop promotion and follow the agreed recovery procedure. Verify the restored version, configuration and active alarm state after recovery. | Jurek checks the running system. Basia verifies recovery if invoked. |

## Executable controls and evidence

For automated gates, use the result emitted by the check. A nonzero exit,
missing result or result bound to a different candidate blocks dependent work.
Record the command or CI check, outcome, commit or digest, configuration
revision where applicable and evidence link. For a scenario, include the
requirement UID, expected and observed result and target alias. Mark failures
and unavailable evidence as failed or blocked. Human approval records the
decision and the candidate, target and actions it covers.

Record release work and outstanding blockers in Beads, with Agent Mail
handoffs keyed by the Beads ID. Keep credentials and private configuration
out of evidence. Follow the [installation, verification and recovery runbook](../safety_component/DOCS.md#verification)
and the [repository authorization rules](../AGENTS.md#ask-first).
For direct AppDaemon directory replacement, preserve the stopped replacement
and file hash checks from [SWR-NFR-007](<sys/SafetyComponent - SSRD.md#5-non-functional-requirements>).
