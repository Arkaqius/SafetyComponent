---
name: safetycomponent-release
description: Prepare, verify, or execute an authorized SafetyComponent release or Home Assistant deployment using candidate, system-test, promotion, and recovery gates.
---

# SafetyComponent release

Read [the release workflow](../../../docs/RELEASE_WORKFLOW.md). Start at the
first gate without evidence for the requested candidate and target. Use the
assigned Beads issue and approved requirements to identify the applicable
scenarios.

1. Resolve the candidate commit, image digest, target alias, configuration
   fingerprint and required checks. Read actual CI results and record links.
2. Prepare the target checks and restoration plan. Send the primary agent
   any missing authorization or evidence. Apply the repository authorization
   rules before each target deployment or live test.
3. Follow the gate order. Record executable exit status and target results.
   Stop dependent steps if a required check fails, lacks evidence or refers
   to another candidate. Use the approved recovery procedure if a deployment
   fails.
4. Record the observed build, configuration, requirement UIDs, results and
   recovery status on the Beads issue. Use its Agent Mail thread to hand off
   the next action to the responsible role.
