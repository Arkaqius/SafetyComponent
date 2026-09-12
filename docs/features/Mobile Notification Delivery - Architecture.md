# Mobile Notification Delivery Architecture

## 1. Purpose

Mobile Notification Delivery converts fault lifecycle events into bounded,
traceable Home Assistant Companion notifications. The feature maintains one
logical notification per fault, delivers new alarms with a severity-specific
profile, refreshes active content quietly, and preserves delivery state across
AppDaemon reloads and restarts.

The delivery boundary is explicit: a successful Home Assistant service call
means **accepted by Home Assistant**. It does not prove that Firebase, Apple
Push Notification Service, or an individual phone delivered or displayed the
message. Diagnostics and logs shall not describe service acceptance as device
delivery.

## 2. Responsibilities

```mermaid
flowchart LR
    FaultManager -->|fault lifecycle event| NotificationManager
    RecoveryManager -->|manual guidance| NotificationManager
    NotificationManager --> MobilePushProvider
    NotificationManager --> LocalAnnunciator
    NotificationManager --> NotificationStateStore
    NotificationManager --> DeliveryScheduler
    MobilePushProvider -->|configured notify services| HomeAssistant
    HomeAssistant -->|mobile_app_notification_action| NotificationManager
    NotificationManager -->|health, counters, and attempt history| MqttEntityManager
```

### 2.1 `NotificationManager`

- owns the active-notification lifecycle and stable fault tag;
- filters fault details through a configured allowlist before presentation;
- distinguishes a new alarm, quiet content refresh, controlled L1 repeat,
  friendly clear, and silent removal;
- treats a same-tag increase in urgency as a new alert, resetting its
  acknowledgement and L1 repeat policy where applicable;
- owns acknowledgement state without clearing the underlying fault;
- queues failed or WAN-blocked deliveries and applies retry policy;
- records deadline telemetry, transport results, and a bounded history of
  individual target submissions;
- persists all state needed to resume safely after a restart.

### 2.2 `MobilePushProvider`

- owns Home Assistant notify service names and Companion payload schemas;
- sends to every explicitly configured service;
- applies Android and iOS profiles for levels L1 through L3;
- uses iOS `time-sensitive` rather than `critical` by default for L1 so the
  stable-tag notification can still be replaced by quiet updates; an
  installation may opt into a critical sound profile when it accepts that
  platform limitation;
- sends the Companion command `message: clear_notification` with the stable
  tag when a notification must be removed;
- requests a Home Assistant service result and reports each configured service
  as `accepted` or `failed`; a missing result is a retryable failure.

The provider shall never fall back to `notify.notify`. Installation routing
shall use an explicit group such as `notify/all_phones` or an explicit list of
mobile notify services.

### 2.3 `LocalAnnunciator`

- owns optional local alarm-panel and light actions;
- runs only for a newly active fault, not for quiet mobile refreshes;
- stores and restores the pre-alert light state where Home Assistant exposes
  enough state to do so;
- does not influence mobile transport success or retry decisions.

### 2.4 `NotificationStateStore`

- writes a versioned JSON snapshot atomically;
- restores active records, acknowledgements, pending deliveries, repeat state,
  counters, last transport result, and submission history;
- retains restored active records until a current fault event confirms SET,
  CLEARED, or SHADOWED, and reconciles an authoritative clear even when the
  fresh FaultManager lifecycle would otherwise suppress a duplicate clear;
- rejects malformed or unsupported snapshots without treating them as a
  positive delivery result;
- stores only filtered notification content, never the unfiltered fault event.

### 2.5 Delivery scheduler

- retries failed service submissions with bounded exponential backoff;
- keeps WAN-blocked items queued until the configured WAN entity recovers;
- performs controlled L1 repeats until acknowledgement or the configured
  repeat bound is reached;
- records whether Home Assistant accepted an attempt after its level deadline.

### 2.6 MQTT diagnostics

`sensor.notification_delivery_health` exposes transport health independently
from fault state. Its state is one of `healthy`, `degraded`, or `queued` and its
attributes include active/acknowledged/queued counts, accepted and failed
attempt counters, deadline misses, last attempt/result/error, per-service
status/time/error, and the explicit statement that device delivery is not
confirmed.

### 2.7 Notification history

The manager shall retain the latest 100 individual target submission attempts,
including successful Home Assistant acceptance and failed submissions. Each
retry shall produce a separate entry only for the targets actually attempted.
Waiting for WAN recovery shall not create a submission-history entry.

`sensor.notification_history` shall expose the retained entry count as its
state, with a versioned history payload, a retention limit of 100, and entries
ordered newest first. The manager shall publish this separate sensor when it
starts and after submission attempts, without rebuilding the journal on idle
scheduler ticks. The shared MQTT heartbeat shall refresh its cached state and
attributes to preserve availability and recover after MQTT restarts.
The journal shall use the existing notification state snapshot and persistence
configuration. A compatible snapshot without history shall restore an empty
journal without discarding active or pending notification state.

Each entry shall contain:

| Field | Meaning |
| --- | --- |
| `id` | Unique UUID for this target attempt. |
| `tag` | Stable fault notification tag for correlation. |
| `kind`, `fault_state` | Submission purpose and associated fault lifecycle state. |
| `title`, `message` | Notification content, each bounded to 2048 characters. |
| `text_truncated` | Whether the stored title or message was shortened to its bound. |
| `level` | Notification severity level. |
| `created_at` | UTC ISO timestamp when this delivery was created. |
| `attempted_at` | UTC ISO timestamp recorded on completion of the submission attempt. |
| `attempt` | Attempt number within this delivery. |
| `service` | Actual configured Home Assistant notify service attempted. |
| `result` | `accepted_by_home_assistant` or `failed`. |
| `deadline_missed` | Whether this delivery exceeded its severity deadline. |

Kinds `new`, `update`, `repeat`, and `acknowledged` shall record `SET`;
`resolved` shall record `CLEARED`; `clear` shall record `SHADOWED`.
Acknowledgement therefore remains visibly distinct from healing. Shadowing
removes a notification and shall not be presented as a healed fault. The journal shall not expose raw
transport exception text, unfiltered fault events, or inferred group members.
Failure details in the history UI shall use a generic diagnostic explanation;
existing transport-health diagnostics retain their separate error contract.

The SafetyHome History page shall present this notification list before entity
history. Each item shall show its date and time, lifecycle state, target
service, and submission outcome. Selecting it shall reveal its content and
diagnostic fields. Dates and times shall be presented in the browser's local
time zone. A notify group shall be identified by its configured service: the
frontend shall not infer which person or device received a group notification.
Home Assistant acceptance shall remain distinct from confirmed device delivery.

## 3. Configuration contract

The installation config owns:

- `mobile.services`: explicit AppDaemon service names in `domain/service` form;
- `mobile.default_url`: Home Assistant-relative destination opened in the
  Companion app from the notification;
- severity profiles for Android and iOS;
- retry limits and backoff;
- L1 repeat interval and maximum repeat count;
- optional WAN-state entity and its online states;
- persistent state-file path;
- additional-info allowlist;
- optional local annunciator entities.

The production default destination is `/5c36e1c9_hakit`; the relative path
keeps notification navigation inside the Companion app. The default transport is
`notify/all_phones`.

Default new-alert profiles are:

| Level | Android channel | Importance / priority | Vibration | iOS interruption |
| --- | --- | --- | --- | --- |
| L1 | `Safety critical` | `max` / `high`, TTL `0` | long urgent pattern | `time-sensitive` |
| L2 | `Safety hazards` | `high` / `high`, TTL `0` | shorter warning pattern | `time-sensitive` |
| L3 | `Safety warnings` | `default` / `normal`, TTL `0` | none | `active` |

Quiet updates, acknowledgement refreshes, and resolved messages override these alert properties with
Android `alert_once`/normal priority and iOS `passive` interruption.

## 4. Lifecycle

### 4.1 New active fault

1. Filter additional details.
2. Build localized content and acknowledgement action.
3. Persist the active record before attempting an external call.
4. Run optional local annunciators once, before any blocking remote submission.
5. If WAN is explicitly offline, queue the attempt.
6. Otherwise submit to every configured mobile service.
7. Record acceptance/failure and deadline telemetry.
8. Schedule bounded L1 repeats when applicable.

### 4.2 Active content refresh

A repeated `SET` or newly discovered recovery guidance updates the same tag.
The refresh uses a quiet profile and shall not re-run local annunciators. On
Android it uses `alert_once`; on iOS it uses a passive interruption profile.
If the new-alert attempt is still pending for any target, its content is
updated without downgrading it to quiet; only targets that already completed
the new-alert submission receive the quiet refresh.

### 4.3 Acknowledgement

The action identifier contains the stable fault tag. A matching
`mobile_app_notification_action` event marks the active record acknowledged,
persists it, cancels future repeats, and quietly replaces the phone notification
without the acknowledgement action. The acknowledgement submission is retained
in notification history. Acknowledgement shall not clear the fault and shall not
prevent later quiet content refreshes.

### 4.4 Fault clear and shadow

A cleared fault publishes a friendly resolved message with a dedicated
localized clear title and the same tag, then removes the active record. A
shadowed fault sends the Companion
`clear_notification` command with the same tag. Pending attempts and scheduled
repeats for that tag are removed in both cases.

## 5. Failure behavior

- Failure of one configured target shall not prevent attempts to other targets.
- A partial target failure is `degraded`, not `healthy`.
- Exhausted retry attempts remain visible in diagnostics and logs.
- WAN state that is missing, unknown, or unavailable shall not be interpreted
  as confirmed connectivity. New remote deliveries remain queued until the
  state becomes one of the configured online states.
- Mobile transport failure shall not block FaultManager, recovery policy, MQTT
  fault state, or local annunciators.

## 6. Verification contract

Automated tests shall cover exact L1-L3 new and quiet payloads, explicit target
routing, correct clear commands, partial failures, retry bounds, WAN queue and
flush, deadlines, acknowledgement, controlled repeats, restart restoration,
allowlist filtering, local-annunciator separation, and diagnostic publication.
History tests shall cover SET and CLEARED entries, distinct shadow removal,
per-target failures and retries, retention bounds, restart restoration and
compatible snapshots without history, content bounds, and publication only on
startup or attempts. Frontend tests shall cover lifecycle labels, date/time and
target presentation, diagnostic details, and empty or unavailable history.

Live verification shall not trigger a household fault, siren, warning light,
or unsolicited phone notification. Production delivery requires a separately
approved controlled test.
