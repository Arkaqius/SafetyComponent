/** Restrict operator restart to the installed App and advertised HA action. */
export function configurationRestartMessage(appSlug: string, services: Record<string, Record<string, unknown>>) {
  if (!/^[A-Za-z0-9_-]{1,128}$/.test(appSlug)) throw new Error('Nieprawidłowy identyfikator aplikacji.');
  if (services.hassio?.app_restart) {
    return { type: 'call_service', domain: 'hassio', service: 'app_restart', service_data: { app: appSlug } };
  }
  if (services.hassio?.addon_restart) {
    return { type: 'call_service', domain: 'hassio', service: 'addon_restart', service_data: { addon: appSlug } };
  }
  throw new Error('Home Assistant nie udostępnia akcji restartu aplikacji.');
}

export function canRestartConfiguration(dirty: boolean, setupRequired: boolean, invalid: boolean, busy: boolean): boolean {
  return !dirty && !setupRequired && !invalid && !busy;
}
