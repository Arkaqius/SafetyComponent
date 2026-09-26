import { useCallback, useEffect, useRef, useState } from 'react';
import { useConfig } from '@hakit/core';
import ConfigurationObjectEditor from '../components/ConfigurationObjectEditor';
import BatteryDiscovery from '../components/BatteryDiscovery';
import { registrySchemas } from '../components/configurationFieldSchemas';
import { importUserConfiguration, loadUserConfiguration, saveUserConfiguration, type ConfigurationMap } from '../userConfigurationApi';

const providerNames = ['OpenMeteoWeatherApiComponent', 'ImgwWarningsApiComponent', 'OpenMeteoAirQualityApiComponent'];
const registrySections = [
  { key: 'rooms', title: 'Pomieszczenia', description: 'Czujniki temperatury, obszary i przypisane otwory.' },
  { key: 'openings', title: 'Drzwi, bramy i okna', description: 'Fizyczne otwory oraz ich role bezpieczeństwa.' },
  { key: 'detectors', title: 'Detektory zagrożeń', description: 'Czujniki dymu, gazu i tlenku węgla.' },
] as const;

type SaveState = 'idle' | 'saving' | 'saved';

export default function Configuration() {
  const haConfig = useConfig();
  const [draft, setDraft] = useState<ConfigurationMap | null>(null);
  const [systemDefaults, setSystemDefaults] = useState<ConfigurationMap>({});
  const [revision, setRevision] = useState('');
  const [setupRequired, setSetupRequired] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<SaveState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const document = await loadUserConfiguration();
      setDraft(document.user_config);
      setSystemDefaults(document.system_defaults ?? {});
      setRevision(document.revision);
      setSetupRequired(document.setup_required);
      setValidationError(document.validation_error ?? null);
      setDirty(false);
      setSaveState('idle');
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Nie udało się pobrać konfiguracji');
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const update = useCallback((path: string[], value: unknown) => {
    setDraft(current => (current ? updatePath(current, path, value) : current));
    setDirty(true);
    setSaveState('idle');
  }, []);

  const save = async () => {
    if (!draft) return;
    setSaveState('saving');
    setError(null);
    try {
      const document = await saveUserConfiguration(draft, revision);
      setDraft(document.user_config);
      setRevision(document.revision);
      setSetupRequired(false);
      setValidationError(null);
      setDirty(false);
      setSaveState('saved');
    } catch (caught) {
      setSaveState('idle');
      setError(caught instanceof Error ? caught.message : 'Nie udało się zapisać konfiguracji');
    }
  };

  const importFile = async (file: File) => {
    if (!/\.ya?ml$/i.test(file.name)) {
      setError('Wybierz plik .yml lub .yaml');
      return;
    }
    if (file.size > 400 * 1024) {
      setError('Plik YAML jest zbyt duży (limit 400 KiB)');
      return;
    }
    setError(null);
    try {
      const imported = await importUserConfiguration(await file.text());
      setDraft(imported);
      setDirty(true);
      setSaveState('idle');
      setValidationError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Nie udało się wczytać pliku');
    }
  };

  if (!draft) {
    return (
      <div className='page-stack'>
        <section className='panel configuration-loading'>
          <strong>{error ? 'Konfiguracja jest niedostępna' : 'Wczytywanie konfiguracji…'}</strong>
          {error ? <p>{error}</p> : null}
          {error ? (
            <button className='primary-button' onClick={() => void load()} type='button'>
              Spróbuj ponownie
            </button>
          ) : null}
        </section>
      </div>
    );
  }

  const components = asMap(draft.components_enabled);
  const localization = asMap(draft.localization);
  const notification = asMap(draft.notification);
  const mobile = asMap(notification.mobile);
  const localNotification = asMap(notification.local);
  const providers = asMap(draft.providers);
  const installation = asMap(draft.installation);
  const site = asMap(installation.site);
  const commonEntities = asMap(installation.common_entities);
  const defaults = asMap(installation.component_settings);
  const temperatureDefaults = asMap(defaults.temperature);
  const safetyDoorDefaults = asMap(defaults.safety_door);
  const entityMonitorDefaults = asMap(defaults.entity_monitor);
  const externalHazardDefaults = asMap(defaults.external_hazard);
  const weatherSettings = asMap(externalHazardDefaults.weather);
  const airQualitySettings = asMap(externalHazardDefaults.outdoor_air_quality);
  const componentOverrides = asMap(entityMonitorDefaults.component_overrides);
  const temperatureSystem = asMap(systemDefaults.temperature);
  const safetyDoorSystem = asMap(systemDefaults.safety_door);
  const entityMonitorSystem = asMap(systemDefaults.entity_monitor);
  const externalHazardSystem = asMap(systemDefaults.external_hazard);
  const weatherSystem = asMap(externalHazardSystem.weather);
  const airQualitySystem = asMap(externalHazardSystem.outdoor_air_quality);
  const detectorProfiles = stringList(systemDefaults.detector_profiles);
  const functionalSafety = asMap(installation.functional_safety);
  const batteryMonitoring = asMap(functionalSafety.battery_monitoring);
  const hostMemory = asMap(functionalSafety.host_memory);
  const backup = asMap(functionalSafety.backup);
  const periodicTests = asMap(functionalSafety.periodic_tests);
  const updates = asMap(functionalSafety.updates);
  const functionalSafetySystem = asMap(systemDefaults.functional_safety);
  const detectorSchema = detectorProfiles.length
    ? {
        ...registrySchemas.detectors,
        profile: {
          ...registrySchemas.detectors.profile,
          kind: 'select' as const,
          options: detectorProfiles.map(profile => [profile, profile] as [string, string]),
          initial: detectorProfiles[0],
        },
      }
    : registrySchemas.detectors;
  const timezones = supportedTimezones(stringValue(site.timezone));

  return (
    <div className='page-stack'>
      <section className='page-introduction configuration-introduction'>
        <div>
          <span className='section-kicker'>Konfiguracja instalacji</span>
          <h2>Ustawienia SafetyComponent</h2>
          <p>
            Edytujesz wyłącznie prywatny <code>user_config.yml</code>. Polityka, kalibracja i parametry wykonawcze z{' '}
            <code>system_config.yml</code> są dostarczane razem z aplikacją. W panelu widać ich wartości domyślne, ale nie można ich tu
            zmienić.
          </p>
        </div>
        <div className='configuration-actions'>
          <a
            className='secondary-button configuration-help-link'
            href='https://github.com/Arkaqius/SafetyComponent/blob/main/frontend/CONFIGURATION.md'
            rel='noopener noreferrer'
            target='_blank'
          >
            Pomoc: opis pól konfiguracji
          </a>
          <input
            accept='.yml,.yaml'
            aria-label='Wybierz plik user_config YAML'
            className='sr-only'
            onChange={event => {
              const file = event.target.files?.[0];
              if (file) void importFile(file);
              event.target.value = '';
            }}
            ref={fileInputRef}
            type='file'
          />
          <button className='secondary-button' onClick={() => fileInputRef.current?.click()} type='button'>
            Wczytaj user_config YAML
          </button>
          <button className='secondary-button' disabled={!dirty || saveState === 'saving'} onClick={() => void load()} type='button'>
            Odrzuć zmiany
          </button>
          <button className='primary-button' disabled={!dirty || saveState === 'saving'} onClick={() => void save()} type='button'>
            {saveState === 'saving' ? 'Zapisywanie…' : setupRequired ? 'Utwórz user_config.yml' : 'Zapisz konfigurację'}
          </button>
        </div>
      </section>

      {setupRequired ? (
        <div className='configuration-message configuration-message-warning'>
          Pierwsza konfiguracja: wypełnij dane instalacji albo wczytaj istniejący plik YAML. SafetyFunctions pozostaje wyłączony do czasu
          zapisania poprawnego pliku i restartu aplikacji.
        </div>
      ) : null}
      {validationError ? (
        <div className='configuration-message configuration-message-error'>
          Zapisany plik wymaga poprawy: {validationError}. Możesz poprawić pola lub wczytać poprawny plik YAML.
        </div>
      ) : null}
      {dirty && !setupRequired ? (
        <div className='configuration-message configuration-message-warning'>
          Masz niezapisane zmiany. Sprawdź wartości i kliknij „Zapisz konfigurację”, aby zastąpić bieżący plik.
        </div>
      ) : null}
      {error ? <div className='configuration-message configuration-message-error'>{error}</div> : null}
      {saveState === 'saved' ? (
        <div className='configuration-message configuration-message-success'>
          Konfiguracja została zapisana i zweryfikowana. Uruchom ponownie aplikację SafetyComponent, aby zastosować zmiany.
        </div>
      ) : null}

      <section className='panel configuration-section'>
        <SectionHeader
          title='Funkcje i integracje'
          description='Włącz komponenty bezpieczeństwa oraz źródła danych używane w tej instalacji.'
        />
        <div className='configuration-columns'>
          <fieldset className='configuration-fieldset'>
            <legend>Komponenty</legend>
            {Object.entries(components).map(([name, enabled]) => (
              <ToggleField
                checked={Boolean(enabled)}
                key={name}
                label={friendlyName(name, 'Component')}
                onChange={value => update(['components_enabled', name], value)}
              />
            ))}
          </fieldset>
          <fieldset className='configuration-fieldset'>
            <legend>Providery API</legend>
            {providerNames.map(name => (
              <ToggleField
                checked={asMap(providers[name]).enabled !== false}
                key={name}
                label={friendlyName(name, 'ApiComponent')}
                onChange={value => update(['providers', name, 'enabled'], value)}
              />
            ))}
          </fieldset>
        </div>
      </section>

      <section className='panel configuration-section'>
        <SectionHeader title='Język' description='Nazwy encji są definiowane w plikach lokalizacji, poza konfiguracją użytkownika.' />
        <div className='configuration-grid'>
          <SelectField
            label='Język'
            help='Język komunikatów i nazw publikowanych przez SafetyComponent.'
            value={stringValue(localization.language, 'pl')}
            onChange={value => update(['localization', 'language'], value)}
            options={[
              ['pl', 'Polski'],
              ['en', 'English'],
              ['de', 'Deutsch'],
            ]}
          />
        </div>
      </section>

      <section className='panel configuration-section'>
        <SectionHeader title='Powiadomienia' description='Miejsca docelowe powiadomień Home Assistant.' />
        <div className='configuration-grid'>
          <TextField
            label='Domyślny adres po kliknięciu powiadomienia'
            help='Ścieżka w Home Assistant otwierana po dotknięciu powiadomienia.'
            defaultValue='/'
            value={stringValue(mobile.default_url)}
            onChange={value => update(['notification', 'mobile', 'default_url'], value)}
          />
          <TextAreaField
            label='Usługi powiadomień (jedna w wierszu)'
            help='Wpisz usługi notify/<nazwa>, dostępne w tej instalacji.'
            value={stringList(mobile.services).join('\n')}
            onChange={value => update(['notification', 'mobile', 'services'], splitLines(value))}
          />
          <TextField
            label='Encja łączności WAN (opcjonalnie)'
            help='Wspólna dla powiadomień i diagnostyki WAN. Stany on/online/connected oznaczają połączenie; off/offline/disconnected — brak. Sam stan nie dowodzi, że każdy serwis w Internecie działa.'
            value={stringValue(notification.wan_entity)}
            onChange={value => update(['notification', 'wan_entity'], value || null)}
          />
          <TextField
            label='Lokalna encja światła (opcjonalnie)'
            value={stringValue(localNotification.light_entity)}
            onChange={value => update(['notification', 'local', 'light_entity'], value || undefined)}
          />
          <TextField
            label='Lokalna encja alarmu (opcjonalnie)'
            value={stringValue(localNotification.alarm_entity)}
            onChange={value => update(['notification', 'local', 'alarm_entity'], value || undefined)}
          />
        </div>
      </section>

      <section className='panel configuration-section'>
        <SectionHeader
          title='Instalacja Home Assistant'
          description='Dane administracyjne i wspólne encje. Współrzędne są pobierane z Home Assistant przy każdym uruchomieniu aplikacji.'
        />
        <p className='configuration-ha-location'>
          Współrzędne HA: {haConfig ? `${haConfig.latitude}, ${haConfig.longitude}` : 'oczekiwanie na Home Assistant'}
        </p>
        <div className='configuration-grid'>
          <SelectField
            label='Strefa czasowa'
            help='Strefa używana do interpretacji lokalnych alertów; współrzędne pochodzą z HA.'
            value={stringValue(site.timezone)}
            onChange={value => update(['installation', 'site', 'timezone'], value)}
            options={timezones.map(zone => [zone, zone])}
          />
          <TextField
            label='Kod kraju'
            help='Dwuliterowy kod kraju dla reguł administracyjnych, np. PL.'
            value={stringValue(site.country_code)}
            onChange={value => update(['installation', 'site', 'country_code'], value.toUpperCase())}
          />
          <TextAreaField
            label='Kody TERYT (jeden w wierszu)'
            help='Czterocyfrowe kody powiatów używane przez ostrzeżenia IMGW.'
            value={stringList(site.teryt_codes).join('\n')}
            onChange={value => update(['installation', 'site', 'teryt_codes'], splitLines(value))}
          />
          <TextField
            label='Encja temperatury zewnętrznej'
            help='Encja używana przez komponent temperatury, jeśli jest włączony.'
            value={stringValue(commonEntities.outside_temp)}
            onChange={value => update(['installation', 'common_entities', 'outside_temp'], value)}
          />
        </div>
      </section>

      <section className='panel configuration-section'>
        <SectionHeader
          title='Zdrowie systemu i konserwacja'
          description='Opcjonalne źródła dla funkcjonalnego monitoringu bezpieczeństwa. Brak encji oznacza brak pokrycia, a nie stan prawidłowy.'
        />
        <p>
          Encja WAN ustawiona w sekcji Powiadomienia służy również do diagnostyki łączności. Czujniki diagnostyczne hosta trzeba najpierw
          włączyć w Home Assistant.
        </p>
        <div className='configuration-grid'>
          <TextField
            label='Pamięć dostępna hosta'
            help='Encja sensor.* podająca dostępną pamięć tego samego hosta co Home Assistant; wymagana razem z PSI.'
            value={stringValue(hostMemory.available_entity)}
            onChange={value => update(['installation', 'functional_safety', 'host_memory', 'available_entity'], value)}
          />
          <TextField
            label='Presja pamięci hosta (PSI, %)'
            help='Encja sensor.* memory PSI some, np. średnia 60 s. Obie encje muszą dotyczyć tego samego hosta.'
            value={stringValue(hostMemory.psi_entity)}
            onChange={value => update(['installation', 'functional_safety', 'host_memory', 'psi_entity'], value)}
          />
        </div>
        <p>
          Systemowe progi pamięci: dostępna ≤ {String(functionalSafetySystem.memory_low_available_mib ?? '—')} MiB i PSI ≥{' '}
          {String(functionalSafetySystem.memory_high_psi_percent ?? '—')}% przez{' '}
          {String(functionalSafetySystem.memory_qualification_seconds ?? '—')} s. Po zmianie konfiguracji uruchom aplikację ponownie.
        </p>
        {functionalSafety.host_memory ? (
          <button
            className='secondary-button'
            onClick={() => update(['installation', 'functional_safety', 'host_memory'], null)}
            type='button'
          >
            Usuń obie encje pamięci
          </button>
        ) : null}
        <div className='configuration-grid'>
          <TextField
            label='Obciążenie CPU hosta (%)'
            help='Opcjonalna encja sensor.* procesora hosta Home Assistant. Wysokie obciążenie jest potwierdzane przez czas z system config.'
            value={stringValue(functionalSafety.host_cpu_entity)}
            onChange={value => update(['installation', 'functional_safety', 'host_cpu_entity'], value || null)}
          />
        </div>
        <p>
          Systemowy próg CPU: ≥ {String(functionalSafetySystem.cpu_high_percent ?? '—')}% przez{' '}
          {String(functionalSafetySystem.cpu_qualification_seconds ?? '—')} s (L4).
        </p>
        <fieldset className='configuration-fieldset'>
          <legend>Dysk, temperatura i kopie zapasowe</legend>
          <div className='configuration-grid'>
            <TextField
              label='Wolne miejsce na dysku hosta'
              help='Opcjonalna encja sensor.* dla dysku Home Assistant, w MiB, GiB lub bajtach. Nie podawaj procentu zajętości.'
              value={stringValue(functionalSafety.host_disk_free_entity)}
              onChange={value => update(['installation', 'functional_safety', 'host_disk_free_entity'], value || null)}
            />
            <TextField
              label='Temperatura hosta (°C)'
              help='Opcjonalna encja sensor.* temperatury procesora lub hosta Home Assistant; nie temperatura pomieszczenia.'
              value={stringValue(functionalSafety.host_temperature_entity)}
              onChange={value => update(['installation', 'functional_safety', 'host_temperature_entity'], value || null)}
            />
            <TextField
              label='Ostatnia udana kopia zapasowa'
              help='Encja sensor.* z datą i czasem ostatniej udanej kopii (nie ostatniej próby). Wypełnienie włącza monitoring backupu.'
              value={stringValue(backup.last_success_entity)}
              onChange={value =>
                update(['installation', 'functional_safety', 'backup'], value ? { ...backup, last_success_entity: value } : null)
              }
            />
            <TextField
              label='Błąd kopii zapasowej (opcjonalnie)'
              help='Encja binary_sensor.*: on oznacza błąd. Najpierw podaj encję ostatniej udanej kopii.'
              value={stringValue(backup.failure_entity)}
              disabled={!backup.last_success_entity}
              onChange={value => update(['installation', 'functional_safety', 'backup', 'failure_entity'], value || null)}
            />
          </div>
          <p>
            Progi systemowe: dysk ≤ {String(functionalSafetySystem.disk_low_free_mib ?? 1024)} MiB, powrót ≥{' '}
            {String(functionalSafetySystem.disk_recovery_free_mib ?? 2048)} MiB; temperatura ≥{' '}
            {String(functionalSafetySystem.host_temperature_high_c ?? 80)}°C, powrót ≤{' '}
            {String(functionalSafetySystem.host_temperature_recovery_c ?? 70)}°C; maksymalny wiek kopii{' '}
            {String(functionalSafetySystem.backup_max_age_hours ?? 48)} h. Progi dostarczane są z aplikacją.
          </p>
          {functionalSafety.backup ? (
            <button
              className='secondary-button'
              type='button'
              onClick={() => update(['installation', 'functional_safety', 'backup'], null)}
            >
              Wyłącz monitoring kopii zapasowych
            </button>
          ) : null}
        </fieldset>
        <fieldset className='configuration-fieldset'>
          <legend>Testy okresowe potwierdzane przez operatora</legend>
          <ToggleField
            label='Przypominaj o sprawdzeniu dostarczenia powiadomień'
            checked={periodicTests.notification_delivery !== false}
            onChange={value => update(['installation', 'functional_safety', 'periodic_tests', 'notification_delivery'], value)}
          />
          <ToggleField
            label='Przypominaj o odtworzeniu backupu na osobnym systemie testowym'
            checked={periodicTests.backup_restore === true}
            onChange={value => update(['installation', 'functional_safety', 'periodic_tests', 'backup_restore'], value)}
          />
          <p>
            Interwały systemowe: powiadomienia {String(functionalSafetySystem.notification_test_interval_days ?? 30)} dni, odtworzenie kopii{' '}
            {String(functionalSafetySystem.backup_restore_test_interval_days ?? 180)} dni. Wynik rzeczywiście wykonanego testu zapiszesz w
            widoku Zdrowie funkcji. Te ustawienia nie wysyłają wiadomości, nie uruchamiają syren i nie odtwarzają backupu.
          </p>
        </fieldset>
        <fieldset className='configuration-fieldset'>
          <legend>Aktualizacje</legend>
          <div className='configuration-grid'>
            {(
              [
                ['home_assistant_core', 'Home Assistant Core'],
                ['home_assistant_os', 'Home Assistant OS'],
                ['home_assistant_supervisor', 'Home Assistant Supervisor'],
                ['safety_component', 'SafetyComponent App'],
              ] as const
            ).map(([key, label]) => (
              <TextField
                key={key}
                label={`Encja aktualizacji: ${label}`}
                help='Opcjonalna encja update.*; dostępna aktualizacja ma poziom informacyjny L4.'
                value={stringValue(updates[key])}
                onChange={value => update(['installation', 'functional_safety', 'updates', key], value || null)}
              />
            ))}
          </div>
        </fieldset>
        <BatteryDiscovery
          enabled={batteryMonitoring.enabled !== false}
          excluded={stringList(batteryMonitoring.excluded_devices)}
          staleAfterSeconds={Number(functionalSafetySystem.battery_stale_after_seconds ?? 86400)}
          onEnabledChange={value => update(['installation', 'functional_safety', 'battery_monitoring', 'enabled'], value)}
          onExcludedChange={value => update(['installation', 'functional_safety', 'battery_monitoring', 'excluded_devices'], value)}
        />
        <details>
          <summary>Zaawansowane: ręczne źródła baterii</summary>
          <ConfigurationObjectEditor
            label='Ręczne źródła baterii'
            description='Jedno urządzenie w jednym wpisie; możesz podać czujnik procentowy, binarny lub oba. Urządzenia wyłączone pomiń albo ustaw Monitoruj urządzenie na nie.'
            value={asMap(functionalSafety.remote_batteries)}
            onChange={value => update(['installation', 'functional_safety', 'remote_batteries'], value)}
            schema={registrySchemas.remote_batteries}
          />
        </details>
        <p>
          Systemowy próg niskiej baterii: {String(functionalSafetySystem.battery_low_percent ?? '—')}%. Testy detektorów są wymagane co{' '}
          {String(functionalSafetySystem.detector_test_interval_days ?? '—')} dni.
        </p>
      </section>

      <section className='panel configuration-section'>
        <SectionHeader
          title='Ustawienia komponentów'
          description='Ustawienia specyficzne dla instalacji. Puste pola używają pokazanej wartości systemowej; ustawienia pojedynczego zasobu mają wyższy priorytet.'
        />
        <fieldset className='configuration-fieldset'>
          <legend>Temperatura</legend>
          <div className='configuration-grid'>
            <NumberField
              label='Minimalna temperatura (°C)'
              optional
              defaultValue={String(temperatureSystem.default_low_temperature_c ?? '')}
              help='Próg dla wszystkich pomieszczeń bez własnego progu.'
              value={numberValue(temperatureDefaults.low_temperature_c)}
              onChange={value => update(['installation', 'component_settings', 'temperature', 'low_temperature_c'], value)}
            />
            <NumberField
              label='Maksymalna temperatura (°C)'
              optional
              defaultValue={String(temperatureSystem.default_high_temperature_c ?? '')}
              help='Próg dla wszystkich pomieszczeń bez własnego progu.'
              value={numberValue(temperatureDefaults.high_temperature_c)}
              onChange={value => update(['installation', 'component_settings', 'temperature', 'high_temperature_c'], value)}
            />
          </div>
        </fieldset>
        <fieldset className='configuration-fieldset'>
          <legend>Drzwi i bramy</legend>
          <NumberField
            label='Timeout drzwi i bram (s)'
            optional
            defaultValue={String(safetyDoorSystem.default_timeout_seconds ?? '')}
            help='Czas, po którym otwarty otwór zgłasza stan alarmowy.'
            value={numberValue(safetyDoorDefaults.timeout_seconds)}
            onChange={value => update(['installation', 'component_settings', 'safety_door', 'timeout_seconds'], value)}
          />
        </fieldset>
        <fieldset className='configuration-fieldset'>
          <legend>Monitoring encji</legend>
          <div className='configuration-grid'>
            <NumberField
              label='Czas ochronny po starcie (s)'
              optional
              defaultValue={String(entityMonitorSystem.default_startup_grace_seconds ?? '')}
              help='Opóźnia zgłaszanie awarii zależności po uruchomieniu.'
              value={numberValue(entityMonitorDefaults.startup_grace_seconds)}
              onChange={value => update(['installation', 'component_settings', 'entity_monitor', 'startup_grace_seconds'], value)}
            />
            <NumberField
              label='Interwał oceny encji (s)'
              optional
              defaultValue={String(entityMonitorSystem.default_evaluation_interval_seconds ?? '')}
              help='Częstotliwość sprawdzania zdrowia monitorowanych encji.'
              value={numberValue(entityMonitorDefaults.evaluation_interval_seconds)}
              onChange={value => update(['installation', 'component_settings', 'entity_monitor', 'evaluation_interval_seconds'], value)}
            />
          </div>
          <ConfigurationObjectEditor
            description='Wyjątki dla zależności należących do komponentów. Monitorowane encje dodatkowe są poniżej.'
            label='Wyjątki monitoringu encji'
            value={componentOverrides}
            schema={registrySchemas.component_overrides}
            onChange={value => update(['installation', 'component_settings', 'entity_monitor', 'component_overrides'], value)}
          />
          <ConfigurationObjectEditor
            label='Dodatkowe monitorowane encje'
            description='Encje używane przez logikę innych komponentów są monitorowane automatycznie. Dodawaj tu tylko pozostałe.'
            value={asMap(installation.monitored_entities)}
            schema={registrySchemas.monitored_entities}
            onChange={value => update(['installation', 'monitored_entities'], value)}
          />
        </fieldset>
        <fieldset className='configuration-fieldset'>
          <legend>Zagrożenia zewnętrzne</legend>
          <p className='configuration-field-help'>
            Lista zagrożeń i horyzont prognozy są ustawieniami systemowymi. Poniżej można zmienić tylko progi dla tej instalacji.
          </p>
          <div className='configuration-grid'>
            {(
              [
                ['frost_watch_c', 'Obserwacja mrozu (°C)'],
                ['frost_warning_c', 'Ostrzeżenie przed mrozem (°C)'],
                ['gust_watch_m_s', 'Obserwacja porywów (m/s)'],
                ['gust_warning_m_s', 'Ostrzeżenie o porywach (m/s)'],
                ['precipitation_warning_mm_h', 'Ostrzeżenie o opadach (mm/h)'],
                ['persistence_seconds', 'Trwałość warunku (s)'],
              ] as const
            ).map(([key, label]) => (
              <NumberField
                key={key}
                label={label}
                optional
                defaultValue={String(weatherSystem[`default_${key}`] ?? '')}
                help='Puste pole używa wartości systemowej.'
                value={numberValue(weatherSettings[key])}
                onChange={value => update(['installation', 'component_settings', 'external_hazard', 'weather', key], value)}
              />
            ))}
            <NumberField
              label='Próg jakości powietrza (AQI)'
              optional
              defaultValue={String(airQualitySystem.default_warning_at ?? '')}
              help='Puste pole używa wartości systemowej.'
              value={numberValue(airQualitySettings.warning_at)}
              onChange={value =>
                update(['installation', 'component_settings', 'external_hazard', 'outdoor_air_quality', 'warning_at'], value)
              }
            />
          </div>
        </fieldset>
      </section>

      {registrySections.map(section => (
        <section className='panel configuration-section' key={section.key}>
          <SectionHeader title={section.title} description={section.description} />
          <ConfigurationObjectEditor
            label={section.title}
            description='Nazwy kluczy są stabilnymi identyfikatorami. Zapis zostanie sprawdzony względem modelu konfiguracji.'
            value={asMap(installation[section.key])}
            schema={section.key === 'detectors' ? detectorSchema : registrySchemas[section.key]}
            onChange={value => update(['installation', section.key], value)}
          />
        </section>
      ))}
    </div>
  );
}

function SectionHeader({ title, description }: { title: string; description: string }) {
  return (
    <div className='panel-header configuration-section-header'>
      <div>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
    </div>
  );
}

function ToggleField({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) {
  return (
    <label className='configuration-toggle'>
      <input checked={checked} onChange={event => onChange(event.target.checked)} type='checkbox' />
      <span>{label}</span>
    </label>
  );
}

function TextField({
  label,
  value,
  onChange,
  help,
  defaultValue,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  help?: string;
  defaultValue?: string;
  disabled?: boolean;
}) {
  return (
    <label className='configuration-field'>
      <span title={help}>{label}</span>
      <input disabled={disabled} onChange={event => onChange(event.target.value)} value={value} />
      <FieldHelp help={help} defaultValue={defaultValue} />
    </label>
  );
}

function NumberField({
  label,
  value,
  optional = false,
  help,
  defaultValue,
  onChange,
}: {
  label: string;
  value: number | undefined;
  optional?: boolean;
  help?: string;
  defaultValue?: string;
  onChange: (value: number | undefined) => void;
}) {
  const [text, setText] = useState(value === undefined ? '' : String(value));

  useEffect(() => {
    setText(value === undefined ? '' : String(value));
  }, [value]);

  return (
    <label className='configuration-field'>
      <span title={help}>{label}</span>
      <input
        inputMode='decimal'
        onBlur={() => {
          if (text === '' && optional) onChange(undefined);
          else if (!Number.isFinite(Number(text))) setText(value === undefined ? '' : String(value));
        }}
        onChange={event => {
          const next = event.target.value;
          setText(next);
          if (next === '' && optional) onChange(undefined);
          else if (Number.isFinite(Number(next))) onChange(Number(next));
        }}
        type='number'
        step='any'
        value={text}
      />
      <FieldHelp help={help} defaultValue={defaultValue} />
    </label>
  );
}

function TextAreaField({
  label,
  value,
  onChange,
  help,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  help?: string;
}) {
  return (
    <label className='configuration-field'>
      <span title={help}>{label}</span>
      <textarea onChange={event => onChange(event.target.value)} rows={4} value={value} />
      <FieldHelp help={help} />
    </label>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
  help,
}: {
  label: string;
  value: string;
  options: Array<[string, string]>;
  onChange: (value: string) => void;
  help?: string;
}) {
  return (
    <label className='configuration-field'>
      <span title={help}>{label}</span>
      <select onChange={event => onChange(event.target.value)} value={value}>
        {options.map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>
            {optionLabel}
          </option>
        ))}
      </select>
      <FieldHelp help={help} />
    </label>
  );
}

function FieldHelp({ help, defaultValue }: { help?: string; defaultValue?: string }) {
  if (!help && !defaultValue) return null;
  return (
    <small className='configuration-field-help'>
      {help}
      {defaultValue ? `${help ? ' ' : ''}Domyślnie: ${defaultValue}.` : ''}
    </small>
  );
}

function asMap(value: unknown): ConfigurationMap {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as ConfigurationMap) : {};
}

function stringValue(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback;
}

function numberValue(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

function splitLines(value: string): string[] {
  return value
    .split('\n')
    .map(item => item.trim())
    .filter(Boolean);
}

function updatePath(source: ConfigurationMap, path: string[], value: unknown): ConfigurationMap {
  const [head, ...tail] = path;
  if (!head) return source;
  const copy = { ...source };
  if (tail.length === 0) {
    if (value === undefined) delete copy[head];
    else copy[head] = value;
    return copy;
  }
  copy[head] = updatePath(asMap(copy[head]), tail, value);
  return copy;
}

function friendlyName(name: string, suffix: string): string {
  return name.replace(new RegExp(`${suffix}$`), '').replace(/([a-z])([A-Z])/g, '$1 $2');
}

function supportedTimezones(current: string): string[] {
  const intl = Intl as typeof Intl & { supportedValuesOf?: (key: string) => string[] };
  const zones = intl.supportedValuesOf?.('timeZone') ?? ['Europe/Warsaw', 'Europe/London', 'UTC'];
  return Array.from(new Set([current, ...zones].filter(Boolean))).sort();
}
