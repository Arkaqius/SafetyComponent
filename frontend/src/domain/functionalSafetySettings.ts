/** Only installation decision calibration, never technical runtime policy. */
export const functionalSafetySettings = [
  [
    'Pamięć hosta',
    [
      ['memory_low_available_mib', 'Niska pamięć dostępna (MiB)'],
      ['memory_recovery_available_mib', 'Pamięć przy powrocie (MiB)'],
      ['memory_high_psi_percent', 'Wysoka presja pamięci PSI (%)'],
      ['memory_recovery_psi_percent', 'PSI przy powrocie (%)'],
      ['memory_qualification_seconds', 'Potwierdzenie braku pamięci (s)'],
      ['memory_recovery_seconds', 'Potwierdzenie powrotu pamięci (s)'],
    ],
  ],
  [
    'CPU i WAN',
    [
      ['cpu_high_percent', 'Wysokie obciążenie CPU (%)'],
      ['cpu_recovery_percent', 'CPU przy powrocie (%)'],
      ['cpu_qualification_seconds', 'Potwierdzenie obciążenia CPU (s)'],
      ['cpu_recovery_seconds', 'Potwierdzenie powrotu CPU (s)'],
      ['wan_qualification_seconds', 'Potwierdzenie utraty WAN (s)'],
      ['wan_recovery_seconds', 'Potwierdzenie powrotu WAN (s)'],
    ],
  ],
  [
    'Dysk i temperatura hosta',
    [
      ['disk_low_free_mib', 'Mało wolnego miejsca (MiB)'],
      ['disk_recovery_free_mib', 'Wolne miejsce przy powrocie (MiB)'],
      ['host_temperature_high_c', 'Wysoka temperatura hosta (°C)'],
      ['host_temperature_recovery_c', 'Temperatura hosta przy powrocie (°C)'],
      ['resource_qualification_seconds', 'Potwierdzenie dysku i temperatury (s)'],
      ['resource_recovery_seconds', 'Potwierdzenie powrotu dysku i temperatury (s)'],
    ],
  ],
  [
    'Baterie, kopie i testy',
    [
      ['battery_low_percent', 'Niska bateria (%)'],
      ['backup_max_age_hours', 'Maksymalny wiek kopii (h)'],
      ['detector_test_interval_days', 'Test detektorów co (dni, maks. 180)'],
      ['notification_test_interval_days', 'Test odbioru powiadomień co (dni)'],
      ['backup_restore_test_interval_days', 'Test odtworzenia kopii co (dni)'],
    ],
  ],
] as const;

export function effectiveFunctionalSafetySettings(defaults: Record<string, unknown>, overrides: Record<string, unknown>) {
  const result = { ...defaults };
  for (const [, fields] of functionalSafetySettings) {
    for (const [key] of fields) {
      const value = overrides[key];
      if (typeof value === 'number' && Number.isFinite(value)) result[key] = value;
    }
  }
  return result;
}
