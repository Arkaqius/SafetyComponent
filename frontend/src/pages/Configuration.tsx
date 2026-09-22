import { useCallback, useEffect, useRef, useState } from 'react';
import { useConfig } from '@hakit/core';
import ConfigurationObjectEditor from '../components/ConfigurationObjectEditor';
import { importUserConfiguration, loadUserConfiguration, saveUserConfiguration, type ConfigurationMap } from '../userConfigurationApi';

const providerNames = ['OpenMeteoWeatherApiComponent', 'ImgwWarningsApiComponent', 'OpenMeteoAirQualityApiComponent'];
const registrySections = [
  { key: 'rooms', title: 'Pomieszczenia', description: 'Czujniki temperatury, obszary i przypisane otwory.' },
  { key: 'openings', title: 'Drzwi, bramy i okna', description: 'Fizyczne otwory oraz ich role bezpieczeństwa.' },
  { key: 'detectors', title: 'Detektory zagrożeń', description: 'Czujniki dymu, gazu i tlenku węgla.' },
] as const;
const registryTemplates: Record<string, ConfigurationMap> = {
  rooms: { area_id: '', temperature_sensor: '', temperature: {} },
  openings: { area_id: '', entity_id: '', friendly_name: '', kind: 'window' },
  detectors: { area_id: '', entity_id: '', friendly_name: '', hazard: 'smoke', profile: '' },
  monitored_entities: { entity_id: '', description: '', enabled: true, checks: {} },
};
const registryHelp: Record<string, string> = {
  area_id: 'Identyfikator obszaru Home Assistant.',
  entity_id: 'Identyfikator encji Home Assistant, np. binary_sensor.drzwi.',
  temperature_sensor: 'Encja pomiaru temperatury w pomieszczeniu.',
  window: 'Stabilny identyfikator otworu z sekcji Drzwi, bramy i okna.',
  actuator: 'Opcjonalna encja cover.* dla komponentu temperatury.',
  friendly_name: 'Nazwa czytelna dla użytkownika.',
  kind: 'Rodzaj otworu.',
  safety_door: 'Dodaj obiekt, aby włączyć rolę monitorowania drzwi.',
  external_hazard: 'Dodaj obiekt, aby włączyć rolę zagrożeń zewnętrznych.',
  hazard: 'Rodzaj zagrożenia wykrywany przez detektor.',
  profile: 'Nazwa profilu detektora z system_config.yml.',
  description: 'Opis celu dodatkowego monitoringu.',
  checks: 'Warunki oceny zdrowia encji.',
};

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
  const mqtt = asMap(draft.mqtt);
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
        <SectionHeader title='Lokalizacja i nazwy' description='Język oraz przyjazne nazwy encji publikowanych przez SafetyComponent.' />
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
        <ConfigurationObjectEditor
          description='Opcjonalne nazwy zamiast nazw domyślnych. Kluczem jest entity_id.'
          label='Nadpisania nazw encji'
          value={asMap(localization.entity_names)}
          newEntry=''
          onChange={value => update(['localization', 'entity_names'], value)}
        />
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
            newEntry={{}}
            onChange={value => update(['installation', 'component_settings', 'entity_monitor', 'component_overrides'], value)}
          />
          <ConfigurationObjectEditor
            label='Dodatkowe monitorowane encje'
            description='Encje używane przez logikę innych komponentów są monitorowane automatycznie. Dodawaj tu tylko pozostałe.'
            value={asMap(installation.monitored_entities)}
            newEntry={registryTemplates.monitored_entities}
            help={registryHelp}
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
            newEntry={registryTemplates[section.key]}
            help={registryHelp}
            onChange={value => update(['installation', section.key], value)}
          />
        </section>
      ))}
      <details className='panel configuration-section'>
        <summary>Konserwacja MQTT — stare encje discovery</summary>
        <p className='configuration-field-help'>
          Po zmianie nazwy lub usunięciu encji wpisz jej dawny identyfikator sensor.*. Przy kolejnym starcie aplikacja opublikuje puste
          retained discovery i stan. Lista nie jest wykrywana automatycznie, ponieważ aplikacja nie przechowuje kompletnego rejestru
          poprzednich identyfikatorów.
        </p>
        <TextAreaField
          label='Encje MQTT do usunięcia (jedna w wierszu)'
          value={stringList(mqtt.legacy_discovery_entity_ids).join('\n')}
          onChange={value => update(['mqtt', 'legacy_discovery_entity_ids'], splitLines(value))}
        />
      </details>
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
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  help?: string;
  defaultValue?: string;
}) {
  return (
    <label className='configuration-field'>
      <span title={help}>{label}</span>
      <input onChange={event => onChange(event.target.value)} value={value} />
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
