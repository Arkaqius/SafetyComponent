import assert from 'node:assert/strict';
import test from 'node:test';
import { canRestartConfiguration, configurationRestartMessage } from './configurationRestart.js';

test('restart only invokes the advertised App action and server-provided target', () => {
  assert.deepEqual(configurationRestartMessage('local_safety_component_dev', { hassio: { app_restart: {} } }), {
    type: 'call_service',
    domain: 'hassio',
    service: 'app_restart',
    service_data: { app: 'local_safety_component_dev' },
  });
  assert.deepEqual(configurationRestartMessage('abc_safety_component', { hassio: { addon_restart: {} } }), {
    type: 'call_service',
    domain: 'hassio',
    service: 'addon_restart',
    service_data: { addon: 'abc_safety_component' },
  });
  assert.throws(() => configurationRestartMessage('other/host', { hassio: { app_restart: {} } }));
  assert.throws(() => configurationRestartMessage('local_safety_component', {}));
});

test('restart blocks unsaved, absent, invalid and busy configurations', () => {
  assert.equal(canRestartConfiguration(false, false, false, false), true);
  for (const flags of [
    [true, false, false, false],
    [false, true, false, false],
    [false, false, true, false],
    [false, false, false, true],
  ] as const)
    assert.equal(canRestartConfiguration(flags[0], flags[1], flags[2], flags[3]), false);
});
