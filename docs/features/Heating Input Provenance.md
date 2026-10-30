# Qualifying heating input provenance

This guide explains how an input producer can satisfy the existing
[generic heating input contract](../HEATING_MONITOR_DELIVERY.md#generic-input-contract).
It adds no runtime fields, controller adapters or automatic rule admission.
Use it before selecting a commissioned heating profile.

## Establish the meaning of each input

For each mapped role, record its physical meaning, source entity, unit, original
observation-time source, acquisition cadence and worst-case delivery delay.
Identify whether it is a measurement, intent or contact indication.

| Evidence | Qualified interpretation |
| --- | --- |
| Physical burner telemetry | Observed burner activity, with its documented CH/DHW scope |
| Reported pump status | The exact status represented by the device; flow or rotation requires corresponding evidence |
| Setpoint or command acknowledgement | Requested setting or command confirmation |
| Room valve feedback or measured heat-path response | Only the physically evidenced room-delivery capability |
| Historical fault record | Recorded past fault; never proof of a currently active fault |
| Source heartbeat | Source contact; never the age of every value in its cache |

Review native status-code meanings against the exact device/firmware evidence.
Operational waiting states, historical faults and maintenance requests have
different meanings. Preserve unknown codes as unknown. A field's friendly
name, supported UI range or apparent unit is not sufficient commissioning
evidence. In particular, distinguish an inter-start waiting period from an
actual minimum burner-on duration.

## Preserve original observation time

An aggregate publication can contain fields sampled at different times. Each
required role needs the original observation time of its own value. A producer
may reuse one timestamp only where the acquisition contract proves that those
fields belong to the same physical observation.

The producer must:

- Advance a field's observation time only after a new valid observation of that
  field, including an unchanged value observed again.
- Preserve the time when serializing or republishing cached values.
- Update only fields actually present and valid in a partial source response.
- Keep invalid values and missing timestamps explicitly unavailable; do not
  substitute zero, false or the current clock.
- Establish its clock after restart before emitting qualified UTC timestamps.
- Document acquisition/transport delay and ensure it fits the rule's timing
  allocation. Timestamping reception of proven live device telemetry requires
  evidence of its acquisition semantics and bounded delay; receiving a cached
  gateway response alone does not provide that evidence.

Neither Home Assistant `last_updated`/`last_reported`, an MQTT receive timestamp,
an aggregate sequence number nor a gateway uptime counter alone proves the
observation age of each field. A sequence may assist upstream replay detection;
the current SafetyComponent binding still requires a supported timestamp.

## Map timestamps through existing selectors

This fictional example selects only the packaged Diagnostic profile. It shows
how a producer can expose a temperature and its original time as separate HA
entities; it does not authorize thermal checks or supply operating limits.

```yaml
installation:
  heating_systems:
    Main:
      friendly_name: Heating system
      profile: Diagnostic
      inputs:
        flow_temperature:
          entity_id: sensor.example_flow_temperature
          unit: °C
          evidence_kind: measurement
          independence_group: example_boiler
          freshness: source_timestamp
          observed_at_entity_id: sensor.example_flow_observed_at
          max_age_seconds: 10
```

The timestamp entity's state can be epoch seconds or a timezone-aware ISO
timestamp. Alternatively, `observed_at_attribute` selects a literal attribute
on the value entity, or on `observed_at_entity_id` when both selectors are set.
Select bounds from the actual source cadence and policy allocation; the example
age is not a recommended installation setting. Never create the timestamp by
stamping every HA state update with the current time.

## Verify before admission

| Scenario | Required evidence/result |
| --- | --- |
| New valid sample with unchanged value | Original observation time advances |
| Cached republish while the device stops reporting | Value time remains unchanged and eventually becomes stale |
| Partial device frame | Unobserved fields retain their previous times |
| Invalid observation | No numeric or boolean clear substitute |
| Source reboot or unsynchronized clock | Qualification remains unavailable until real observations and valid time return |
| Retained/replayed source snapshot | Does not gain a new observation time |
| One fresh field with another old field | Independent ages remain visible; incoherent inputs cannot qualify a rule |
| Physical condition recovers | Required positive observations qualify the configured recovery interval |

After source qualification, commission the policy using the
[R07..R12 contracts](<Heating Additional Rule Policies.md>) and the demand/output
contracts in the delivery guide. Hardware topology, native hysteresis, mode
priority, room inertia, narrow recovery bands and the complete response budget
must be justified separately. A working timestamp does not establish safe
temperature limits or independent room-delivery evidence.
