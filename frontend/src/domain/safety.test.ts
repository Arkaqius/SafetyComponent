import assert from 'node:assert/strict';
import test from 'node:test';
import { requestExternalAuthToken, type ExternalAuthHost } from '../auth/externalAuth.js';
import {
  getFaults,
  getMonitoredTemperatures,
  getRecoveries,
  getSafetyDoors,
  getSafetySummary,
  normalizeState,
  recoveryNeedsAttention,
  systemStatePresentation,
  type EntityMap,
} from './safety.js';

const timestamp = '2026-07-29T08:00:00+02:00';

function entity(state: string, attributes: Record<string, unknown> = {}) {
  return { state, attributes, last_changed: timestamp, last_updated: timestamp };
}

test('normalizes Home Assistant states without treating unknown as safe', () => {
  assert.equal(normalizeState('DO_NOT_PERFORM'), 'do_not_perform');
  assert.equal(normalizeState('Not tested'), 'not_tested');
  assert.equal(normalizeState(undefined), '');
});

test('uses Companion App V2 external authentication when available', async () => {
  const host: ExternalAuthHost = {
    externalAppV2: {
      postMessage(message) {
        const request = JSON.parse(message) as {
          type: string;
          payload: { callback: string; force: boolean };
        };
        assert.equal(request.type, 'getExternalAuth');
        assert.equal(request.payload.callback, 'externalAuthSetToken');
        assert.equal(request.payload.force, true);
        host.externalAuthSetToken?.(true, {
          access_token: 'companion-token',
          expires_in: 1800,
        });
      },
    },
  };

  const result = await requestExternalAuthToken(host, { force: true });

  assert.deepEqual(result, {
    supported: true,
    token: {
      accessToken: 'companion-token',
      expiresIn: 1800,
    },
  });
});

test('uses the main frame Companion bridge when rendered in a webpage dashboard iframe', async () => {
  const mainFrame: ExternalAuthHost = {
    externalAppV2: {
      postMessage(message) {
        const request = JSON.parse(message) as {
          type: string;
          payload: { callback: string; force?: boolean };
        };
        assert.equal(request.type, 'getExternalAuth');
        assert.equal(request.payload.callback, 'externalAuthSetToken');
        assert.equal('force' in request.payload, false);
        assert.equal(typeof mainFrame.externalAuthSetToken, 'function');
        mainFrame.externalAuthSetToken?.(true, {
          access_token: 'main-frame-token',
          expires_in: 1800,
        });
      },
    },
  };
  mainFrame.top = mainFrame;
  const iframe: ExternalAuthHost = {
    top: mainFrame,
    externalAppV2: {
      postMessage() {
        assert.fail('The iframe bridge must not be used for external authentication.');
      },
    },
  };

  const result = await requestExternalAuthToken(iframe);

  assert.deepEqual(result, {
    supported: true,
    token: {
      accessToken: 'main-frame-token',
      expiresIn: 1800,
    },
  });
  assert.equal(iframe.externalAuthSetToken, undefined);
});

test('falls back to browser authentication without a Companion bridge', async () => {
  assert.deepEqual(await requestExternalAuthToken({}, { timeoutMs: 1 }), {
    supported: false,
  });
});

test('discovers faults from MQTT entity IDs and orders active faults first', () => {
  const entities: EntityMap = {
    'sensor.fault_notice': entity('Cleared', { level: 'level_4' }),
    'sensor.fault_hazard': entity('Set', {
      friendly_name: 'Safety Component Fault: RiskyTemperature',
      level: 'level_2',
      location: 'Office, Bedroom',
    }),
  };

  const faults = getFaults(entities);
  assert.equal(faults.length, 2);
  assert.equal(faults[0].entityId, 'sensor.fault_hazard');
  assert.equal(faults[0].level, 2);
  assert.deepEqual(faults[0].locations, ['Office', 'Bedroom']);
});

test('only TO_PERFORM recovery states are actionable', () => {
  const recoveries = getRecoveries({
    'sensor.recovery_manipulatewindowbedroom': entity('DO_NOT_PERFORM', {
      friendly_name: 'Safety Component Recovery ManipulateWindowBedroom',
    }),
    'sensor.recovery_manipulatewindowoffice': entity('TO_PERFORM', {
      friendly_name: 'Safety Component Recovery ManipulateWindowOffice',
    }),
  });

  assert.equal(recoveries[0].status, 'to_perform');
  assert.equal(recoveries[0].name, 'Office');
  assert.equal(recoveries[1].status, 'do_not_perform');
});

test('treats unavailable and unknown recovery states as requiring attention', () => {
  const recoveries = getRecoveries({
    'sensor.recovery_manipulatewindowoffice': entity('unavailable'),
    'sensor.recovery_manipulatewindowbedroom': entity('unexpected-state'),
    'sensor.recovery_manipulatewindowgarage': entity('DO_NOT_PERFORM'),
  });

  assert.deepEqual(recoveries.map(recoveryNeedsAttention), [true, true, false]);
});

test('discovers monitored temperature from SafetyComponent derivative pair', () => {
  const entities: EntityMap = {
    'sensor.office_climatesensor_temperature': entity('23.25', {
      friendly_name: 'Biuro',
      unit_of_measurement: '°C',
    }),
    'sensor.office_climatesensor_temperature_rate': entity('-0.015', {
      unit_of_measurement: '°C/min',
      attribution: 'Data provided by SafetyFunction',
    }),
    'sensor.office_climatesensor_temperature_rateofrate': entity('0.001', {
      unit_of_measurement: '°C/min²',
    }),
    'sensor.office_climatesensor_temperature_low_threshold': entity('18', {
      source_entity: 'sensor.office_climatesensor_temperature',
      threshold_type: 'low',
      unit_of_measurement: '°C',
    }),
    'sensor.office_climatesensor_temperature_high_threshold': entity('28', {
      source_entity: 'sensor.office_climatesensor_temperature',
      threshold_type: 'high',
      unit_of_measurement: '°C',
    }),
  };

  const temperatures = getMonitoredTemperatures(entities);
  assert.equal(temperatures.length, 1);
  assert.equal(temperatures[0].state, 23.25);
  assert.equal(temperatures[0].rate, -0.015);
  assert.equal(temperatures[0].acceleration, 0.001);
  assert.equal(temperatures[0].lowThreshold, 18);
  assert.equal(temperatures[0].highThreshold, 28);
});

test('discovers only configured Safety Doors MQTT entities', () => {
  const doors = getSafetyDoors({
    'sensor.safety_door_garagegate': entity('active', {
      friendly_name: 'Safety Door: GarageGate',
      source_entity: 'binary_sensor.garage_gate',
      door_state: 'open',
      timeout_seconds: 120,
      open_duration_seconds: 145,
      remaining_seconds: 0,
      opened_at: '2026-07-29T07:57:35+00:00',
    }),
    'sensor.safety_door_terracedoor': entity('blocked', {
      friendly_name: 'Safety Door: TerraceDoor',
      source_entity: 'binary_sensor.terrace_door',
      door_state: 'open',
      timeout_seconds: 120,
      open_duration_seconds: 0,
      remaining_seconds: 120,
      opened_at: null,
      condition_entity: 'sensor.home_monitor_occupancy',
      condition_state: 'occupied',
      condition_result: 'blocked',
    }),
    'binary_sensor.garage_gate': entity('on', {
      friendly_name: 'Brama garażowa',
    }),
    'binary_sensor.terrace_door': entity('on', {
      friendly_name: 'Drzwi tarasowe w salonie',
    }),
    'sensor.home_monitor_occupancy': entity('occupied', {
      friendly_name: 'Obecność w domu',
    }),
    'binary_sensor.unconfigured_door': entity('on'),
  });

  assert.equal(doors.length, 2);
  assert.equal(doors[0].name, 'Garage Gate');
  assert.equal(doors[0].status, 'active');
  assert.equal(doors[0].doorState, 'open');
  assert.equal(doors[0].timeoutSeconds, 120);
  assert.equal(doors[0].sourceEntityId, 'binary_sensor.garage_gate');
  assert.equal(doors[0].sourceEntityName, 'Brama garażowa');
  assert.equal(doors[1].status, 'blocked');
  assert.equal(doors[1].sourceEntityName, 'Drzwi tarasowe w salonie');
  assert.equal(doors[1].conditionEntityId, 'sensor.home_monitor_occupancy');
  assert.equal(doors[1].conditionEntityName, 'Obecność w domu');
  assert.equal(doors[1].conditionState, 'occupied');
  assert.equal(doors[1].conditionResult, 'blocked');
  assert.equal(doors[1].remainingSeconds, 120);
});

test('maps level 1 as the most severe active fault', () => {
  const faults = getFaults({
    'sensor.fault_warning': entity('Set', { level: 'level_3' }),
    'sensor.fault_emergency': entity('Set', { level: 'level_1' }),
  });
  const summary = getSafetySummary(entity('running'), entity('warning'), faults, []);

  assert.equal(summary.effectiveLevel, 1);
  assert.equal(summary.label, 'Alarm krytyczny');
  assert.equal(summary.tone, 'critical');
});

test('maps semantic system states while retaining numeric compatibility', () => {
  const semanticSummary = getSafetySummary(
    entity('running'),
    entity('hazard'),
    [],
    []
  );
  const legacySummary = getSafetySummary(entity('running'), entity('2'), [], []);

  assert.equal(semanticSummary.effectiveLevel, 2);
  assert.equal(legacySummary.effectiveLevel, 2);
  assert.equal(systemStatePresentation('no_faults').label, 'Brak aktywnych usterek');
});

test('never reports a missing system entity as safe', () => {
  const summary = getSafetySummary(entity('running'), undefined, [], []);
  assert.equal(summary.label, 'Dane niedostępne');
  assert.equal(summary.tone, 'muted');
});

test('never reports uncertain fault or recovery data as safe', () => {
  const uncertainFaults = getFaults({
    'sensor.fault_riskytemperature': entity('unavailable', { level: 'level_2' }),
  });
  const uncertainRecoveries = getRecoveries({
    'sensor.recovery_manipulatewindowoffice': entity('unexpected-state'),
  });
  const summary = getSafetySummary(entity('running'), entity('0'), uncertainFaults, uncertainRecoveries);

  assert.equal(summary.label, 'Dane niepełne');
  assert.equal(summary.tone, 'muted');
});

test('never maps a malformed system level to a safe state', () => {
  const summary = getSafetySummary(entity('running'), entity('corrupt'), [], []);

  assert.equal(summary.label, 'Dane niepełne');
  assert.equal(summary.effectiveLevel, null);
  assert.equal(summary.tone, 'muted');
});

test('escalates an active fault when another fault state is uncertain', () => {
  const faults = getFaults({
    'sensor.fault_notice': entity('Set', { level: 'level_4' }),
    'sensor.fault_emergency': entity('unavailable', { level: 'level_1' }),
  });
  const summary = getSafetySummary(entity('running'), entity('4'), faults, []);

  assert.equal(summary.label, 'Aktywna usterka · dane niepełne');
  assert.equal(summary.effectiveLevel, null);
  assert.equal(summary.tone, 'critical');
});

test('does not trust an aggregate severity when an active fault has no level attribute', () => {
  const faults = getFaults({
    'sensor.fault_riskytemperature': entity('Set'),
  });
  const summary = getSafetySummary(entity('running'), entity('3'), faults, []);

  assert.equal(summary.label, 'Aktywna usterka');
  assert.equal(summary.effectiveLevel, null);
  assert.equal(summary.tone, 'danger');
});
