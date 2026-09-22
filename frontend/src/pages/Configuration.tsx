import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from 'react';
import { importUserConfiguration, loadUserConfiguration, saveUserConfiguration, type ConfigurationMap } from '../userConfigurationApi';

const providerNames = ['OpenMeteoWeatherApiComponent', 'ImgwWarningsApiComponent', 'OpenMeteoAirQualityApiComponent'];
const registrySections = [
  { key: 'rooms', title: 'Pomieszczenia', description: 'Czujniki temperatury, obszary i przypisane otwory.' },
  { key: 'openings', title: 'Drzwi, bramy i okna', description: 'Fizyczne otwory oraz ich role bezpieczeństwa.' },
  { key: 'detectors', title: 'Detektory zagrożeń', description: 'Czujniki dymu, gazu i tlenku węgla.' },
  { key: 'monitored_entities', title: 'Monitorowane encje', description: 'Jawnie nadzorowane encje i ich kryteria zdrowia.' },
] as const;

type SaveState = 'idle' | 'saving' | 'saved';

export default function Configuration() {
  const [draft, setDraft] = useState<ConfigurationMap | null>(null);
  const [revision, setRevision] = useState('');
  const [setupRequired, setSetupRequired] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<SaveState>('idle');
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [editorErrors, setEditorErrors] = useState<Record<string, string>>({});
  const [editorGeneration, setEditorGeneration] = useState(0);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const document = await loadUserConfiguration();
      setDraft(document.user_config);
      setRevision(document.revision);
      setSetupRequired(document.setup_required);
      setValidationError(document.validation_error ?? null);
      setDirty(false);
      setSaveState('idle');
      setEditorErrors({});
      setEditorGeneration(current => current + 1);
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
    if (!draft || Object.keys(editorErrors).length > 0) return;
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
      setEditorErrors({});
      setValidationError(null);
      setEditorGeneration(current => current + 1);
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
  const defaults = asMap(installation.defaults);
  const temperatureDefaults = asMap(defaults.temperature);
  const safetyDoorDefaults = asMap(defaults.safety_door);
  const entityMonitorDefaults = asMap(defaults.entity_monitor);
  const externalHazardDefaults = asMap(defaults.external_hazard);
  const componentOverrides = asMap(entityMonitorDefaults.component_overrides);

  return (
    <div className='page-stack'>
      <section className='page-introduction configuration-introduction'>
        <div>
          <span className='section-kicker'>Konfiguracja instalacji</span>
          <h2>Ustawienia SafetyComponent</h2>
          <p>
            Edytujesz wyłącznie prywatny <code>user_config.yml</code>. Polityka, kalibracja i parametry wykonawcze z{' '}
            <code>system_config.yml</code> są dostarczane razem z aplikacją i nie są dostępne w tym panelu.
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
          <button
            className='primary-button'
            disabled={!dirty || saveState === 'saving' || Object.keys(editorErrors).length > 0}
            onClick={() => void save()}
            type='button'
          >
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
        <SectionHeader title='Ustawienia użytkownika' description='Język interfejsu i miejsca docelowe powiadomień Home Assistant.' />
        <div className='configuration-grid'>
          <SelectField
            label='Język'
            value={stringValue(localization.language, 'pl')}
            onChange={value => update(['localization', 'language'], value)}
            options={[
              ['pl', 'Polski'],
              ['en', 'English'],
              ['de', 'Deutsch'],
            ]}
          />
          <TextField
            label='Domyślny adres po kliknięciu powiadomienia'
            value={stringValue(mobile.default_url)}
            onChange={value => update(['notification', 'mobile', 'default_url'], value)}
          />
          <TextAreaField
            label='Usługi powiadomień (jedna w wierszu)'
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
          <TextAreaField
            label='Encje MQTT do jednorazowego posprzątania'
            value={stringList(mqtt.legacy_discovery_entity_ids).join('\n')}
            onChange={value => update(['mqtt', 'legacy_discovery_entity_ids'], splitLines(value))}
          />
        </div>
        <JsonObjectEditor
          description='Opcjonalne przyjazne nazwy encji publikowanych przez SafetyComponent.'
          key={`entity-names-${editorGeneration}`}
          label='Nadpisania nazw encji'
          value={asMap(localization.entity_names)}
          onChange={value => update(['localization', 'entity_names'], value)}
          onError={message => setEditorError(setEditorErrors, 'entity_names', message)}
        />
      </section>

      <section className='panel configuration-section'>
        <SectionHeader
          title='Instalacja Home Assistant'
          description='Lokalizacja oraz wspólne encje dostępne dla wszystkich komponentów.'
        />
        <div className='configuration-grid'>
          <NumberField
            label='Szerokość geograficzna'
            value={numberValue(site.latitude)}
            onChange={value => update(['installation', 'site', 'latitude'], value)}
          />
          <NumberField
            label='Długość geograficzna'
            value={numberValue(site.longitude)}
            onChange={value => update(['installation', 'site', 'longitude'], value)}
          />
          <TextField
            label='Strefa czasowa'
            value={stringValue(site.timezone)}
            onChange={value => update(['installation', 'site', 'timezone'], value)}
          />
          <TextField
            label='Kod kraju'
            value={stringValue(site.country_code)}
            onChange={value => update(['installation', 'site', 'country_code'], value.toUpperCase())}
          />
          <TextAreaField
            label='Kody TERYT (jeden w wierszu)'
            value={stringList(site.teryt_codes).join('\n')}
            onChange={value => update(['installation', 'site', 'teryt_codes'], splitLines(value))}
          />
          <TextField
            label='Encja temperatury zewnętrznej'
            value={stringValue(commonEntities.outside_temp)}
            onChange={value => update(['installation', 'common_entities', 'outside_temp'], value)}
          />
        </div>
      </section>

      <section className='panel configuration-section'>
        <SectionHeader
          title='Domyślne wartości instalacji'
          description='Nadpisują wartości systemowe dla całej instalacji. Ustawienia pojedynczego zasobu mają wyższy priorytet.'
        />
        <div className='configuration-grid'>
          <NumberField
            label='Minimalna temperatura (°C)'
            optional
            value={numberValue(temperatureDefaults.low_temperature_c)}
            onChange={value => update(['installation', 'defaults', 'temperature', 'low_temperature_c'], value)}
          />
          <NumberField
            label='Maksymalna temperatura (°C)'
            optional
            value={numberValue(temperatureDefaults.high_temperature_c)}
            onChange={value => update(['installation', 'defaults', 'temperature', 'high_temperature_c'], value)}
          />
          <NumberField
            label='Horyzont prognozy (h)'
            optional
            value={numberValue(temperatureDefaults.forecast_horizon_hours)}
            onChange={value => update(['installation', 'defaults', 'temperature', 'forecast_horizon_hours'], value)}
          />
          <NumberField
            label='Timeout drzwi i bram (s)'
            optional
            value={numberValue(safetyDoorDefaults.timeout_seconds)}
            onChange={value => update(['installation', 'defaults', 'safety_door', 'timeout_seconds'], value)}
          />
          <NumberField
            label='Czas ochronny po starcie (s)'
            optional
            value={numberValue(entityMonitorDefaults.startup_grace_seconds)}
            onChange={value => update(['installation', 'defaults', 'entity_monitor', 'startup_grace_seconds'], value)}
          />
          <NumberField
            label='Interwał oceny encji (s)'
            optional
            value={numberValue(entityMonitorDefaults.evaluation_interval_seconds)}
            onChange={value => update(['installation', 'defaults', 'entity_monitor', 'evaluation_interval_seconds'], value)}
          />
        </div>
        <div className='configuration-columns'>
          <JsonObjectEditor
            description='Lista zagrożeń oraz progi pogody i jakości powietrza.'
            key={`external-hazard-${editorGeneration}`}
            label='Domyślne zagrożenia zewnętrzne'
            value={externalHazardDefaults}
            onChange={value => update(['installation', 'defaults', 'external_hazard'], value)}
            onError={message => setEditorError(setEditorErrors, 'external_hazard', message)}
          />
          <JsonObjectEditor
            description='Wyjątki nadzoru zależności należących do komponentów.'
            key={`component-overrides-${editorGeneration}`}
            label='Wyjątki monitoringu encji'
            value={componentOverrides}
            onChange={value => update(['installation', 'defaults', 'entity_monitor', 'component_overrides'], value)}
            onError={message => setEditorError(setEditorErrors, 'component_overrides', message)}
          />
        </div>
      </section>

      {registrySections.map(section => (
        <section className='panel configuration-section' key={section.key}>
          <SectionHeader title={section.title} description={section.description} />
          <JsonObjectEditor
            key={`${section.key}-${editorGeneration}`}
            label={`${section.title} — dane źródłowe`}
            description='Nazwy kluczy są stabilnymi identyfikatorami. Zapis zostanie sprawdzony względem modelu konfiguracji.'
            value={asMap(installation[section.key])}
            onChange={value => update(['installation', section.key], value)}
            onError={message => setEditorError(setEditorErrors, section.key, message)}
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

function TextField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className='configuration-field'>
      <span>{label}</span>
      <input onChange={event => onChange(event.target.value)} value={value} />
    </label>
  );
}

function NumberField({
  label,
  value,
  optional = false,
  onChange,
}: {
  label: string;
  value: number | undefined;
  optional?: boolean;
  onChange: (value: number | undefined) => void;
}) {
  const [text, setText] = useState(value === undefined ? '' : String(value));

  useEffect(() => {
    setText(value === undefined ? '' : String(value));
  }, [value]);

  return (
    <label className='configuration-field'>
      <span>{label}</span>
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
        value={text}
      />
    </label>
  );
}

function TextAreaField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return (
    <label className='configuration-field'>
      <span>{label}</span>
      <textarea onChange={event => onChange(event.target.value)} rows={4} value={value} />
    </label>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: Array<[string, string]>;
  onChange: (value: string) => void;
}) {
  return (
    <label className='configuration-field'>
      <span>{label}</span>
      <select onChange={event => onChange(event.target.value)} value={value}>
        {options.map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>
            {optionLabel}
          </option>
        ))}
      </select>
    </label>
  );
}

function JsonObjectEditor({
  label,
  description,
  value,
  onChange,
  onError,
}: {
  label: string;
  description: string;
  value: ConfigurationMap;
  onChange: (value: ConfigurationMap) => void;
  onError: (message: string | null) => void;
}) {
  const [text, setText] = useState(() => JSON.stringify(value, null, 2));
  const [parseError, setParseError] = useState<string | null>(null);

  return (
    <label className='configuration-json-editor'>
      <span>{label}</span>
      <small>{description}</small>
      {parseError ? <small className='configuration-editor-error'>{parseError}</small> : null}
      <textarea
        spellCheck={false}
        value={text}
        onChange={event => {
          const nextText = event.target.value;
          setText(nextText);
          try {
            const parsed: unknown = JSON.parse(nextText);
            if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('Wymagany jest obiekt JSON');
            setParseError(null);
            onError(null);
            onChange(parsed as ConfigurationMap);
          } catch (caught) {
            const message = caught instanceof Error ? caught.message : 'Nieprawidłowy JSON';
            setParseError(message);
            onError(message);
          }
        }}
      />
    </label>
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

function setEditorError(setter: Dispatch<SetStateAction<Record<string, string>>>, key: string, message: string | null) {
  setter(current => {
    const next = { ...current };
    if (message) next[key] = message;
    else delete next[key];
    return next;
  });
}

function friendlyName(name: string, suffix: string): string {
  return name.replace(new RegExp(`${suffix}$`), '').replace(/([a-z])([A-Z])/g, '$1 $2');
}
