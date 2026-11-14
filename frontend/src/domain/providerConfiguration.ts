/** Typed, bounded provider metadata and immutable installation-draft operations. */
export type ProviderDraft = Record<string, unknown>;
export const EXTERNAL_CAPABILITIES = ['WeatherPointModel', 'OfficialWeatherWarnings', 'OutdoorAirQuality'] as const;
export type ExternalCapability = (typeof EXTERNAL_CAPABILITIES)[number];
export interface ProviderFieldError {
  path: (string | number)[];
  code: string;
  message: string;
}
export interface ProviderField {
  kind: 'string' | 'boolean' | 'number' | 'integer' | 'enum' | 'string_array';
  title: string;
  description: string;
  nullable: boolean;
  required: boolean;
  default?: unknown;
  enum?: string[];
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
  minItems?: number;
  maxItems?: number;
  uniqueItems?: boolean;
  item?: Pick<ProviderField, 'minLength' | 'maxLength' | 'pattern'>;
}
export interface ProviderDefinition {
  id: string;
  dataKind: 'live' | 'synthetic';
  transportKind: 'http' | 'none';
  countries: string[];
  capability: string;
  hazards: string[];
  displayName: string;
  description: string;
  fields: Record<string, ProviderField>;
  requiredWhenSelected: string[];
  defaults: ProviderDraft;
}
export interface ProviderCatalogue {
  providers: Record<string, ProviderDefinition>;
  errors: Record<string, string>;
  error?: string;
}
export interface ProviderCategoryRow {
  capability: ExternalCapability;
  label: string;
  selected: string | null | undefined;
  plugin?: ProviderDefinition;
  options: ProviderDefinition[];
  error?: string;
}
export const CATEGORY_LABELS: Record<ExternalCapability, string> = {
  WeatherPointModel: 'Pogoda',
  OfficialWeatherWarnings: 'Oficjalne ostrzeżenia pogodowe',
  OutdoorAirQuality: 'Jakość powietrza',
};

const forbiddenKeys = new Set(['__proto__', 'constructor', 'prototype']);
const capabilities = new Set(['WeatherPointModel', 'OfficialWeatherWarnings', 'OutdoorAirQuality']);
const weatherHazards = new Set(['frost', 'wind', 'rain', 'storm']);
const bytes = (value: unknown) => new TextEncoder().encode(JSON.stringify(value)).length;
const has = (value: object, key: string) => Object.prototype.hasOwnProperty.call(value, key);
const record = (value: unknown): ProviderDraft =>
  value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as ProviderDraft) : {};
function safeKey(value: string): boolean {
  return value.length > 0 && value.length <= 128 && !forbiddenKeys.has(value);
}
function checkedText(value: unknown, limit: number, fallback = ''): string {
  if (value === undefined) return fallback;
  if (typeof value !== 'string' || value.length > limit) throw new Error('Nieprawidłowy tekst metadanych.');
  return value;
}
function strings(value: unknown, limit: number, required = true): string[] {
  if (value === undefined && !required) return [];
  if (!Array.isArray(value) || value.length > limit || value.some(item => typeof item !== 'string' || !safeKey(item)))
    throw new Error('Nieprawidłowa lista metadanych.');
  if (new Set(value).size !== value.length) throw new Error('Powtórzone wartości metadanych.');
  return value as string[];
}
function depth(value: unknown, level = 0): void {
  if (level > 8) throw new Error('Zbyt głębokie metadane.');
  if (value !== null && typeof value === 'object') for (const item of Object.values(value)) depth(item, level + 1);
}
function resolveSchema(value: unknown, root: ProviderDraft, refs: string[] = []): ProviderDraft {
  let schema = record(value);
  if (typeof schema.$ref === 'string') {
    const reference = schema.$ref;
    if (!reference.startsWith('#/$defs/') || refs.includes(reference) || refs.length >= 16)
      throw new Error('Nieobsługiwane odwołanie schematu.');
    const key = reference.slice(8).replace(/~1/g, '/').replace(/~0/g, '~');
    if (!has(record(root.$defs), key)) throw new Error('Brak definicji schematu.');
    schema = { ...resolveSchema(record(root.$defs)[key], root, [...refs, reference]), ...schema };
    delete schema.$ref;
  }
  return schema;
}
function pattern(value: unknown): string | undefined {
  if (value === undefined) return undefined;
  const text = checkedText(value, 256);
  if (/\\[1-9]|\(\?[=!<]|\([^)]*[+*][^)]*\)[+*{]/.test(text)) throw new Error('Nieobsługiwany wzorzec pola.');
  new RegExp(text);
  return text;
}
function limit(schema: ProviderDraft, key: string): number | undefined {
  const value = schema[key];
  if (value === undefined) return undefined;
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error('Nieprawidłowa granica pola.');
  return value;
}
function decodeField(value: unknown, root: ProviderDraft, name: string, required: boolean): ProviderField {
  let schema = resolveSchema(value, root);
  let nullable = false;
  if (Array.isArray(schema.anyOf)) {
    const other = schema.anyOf.filter(item => record(item).type !== 'null');
    if (schema.anyOf.length !== 2 || other.length !== 1) throw new Error('Nieobsługiwany wariant pola.');
    nullable = true;
    schema = { ...schema, ...resolveSchema(other[0], root) };
  }
  if (schema.oneOf || schema.allOf || schema.not || schema.if) throw new Error('Nieobsługiwany wariant pola.');
  const type = schema.type;
  if (!['string', 'boolean', 'number', 'integer', 'array'].includes(String(type))) throw new Error('Nieobsługiwany typ pola.');
  let kind = type as ProviderField['kind'];
  let options: string[] | undefined;
  if (schema.enum !== undefined) {
    if (type !== 'string' || !Array.isArray(schema.enum) || schema.enum.length > 1024 || !schema.enum.length)
      throw new Error('Nieprawidłowe opcje pola.');
    options = schema.enum.map(item => checkedText(item, 256));
    if (new Set(options).size !== options.length) throw new Error('Powtórzone opcje pola.');
    kind = 'enum';
  }
  let item: ProviderField['item'];
  if (type === 'array') {
    const itemSchema = resolveSchema(schema.items, root);
    if (itemSchema.type !== 'string' || itemSchema.anyOf || itemSchema.enum) throw new Error('Nieobsługiwana lista pola.');
    kind = 'string_array';
    item = { minLength: limit(itemSchema, 'minLength'), maxLength: limit(itemSchema, 'maxLength'), pattern: pattern(itemSchema.pattern) };
  }
  const field: ProviderField = {
    kind,
    title: checkedText(schema.title, 256, name),
    description: checkedText(schema.description, 2048),
    nullable,
    required,
    default: schema.default,
    enum: options,
    item,
    minLength: limit(schema, 'minLength'),
    maxLength: limit(schema, 'maxLength'),
    pattern: pattern(schema.pattern),
    minimum: limit(schema, 'minimum'),
    maximum: limit(schema, 'maximum'),
    exclusiveMinimum: limit(schema, 'exclusiveMinimum'),
    exclusiveMaximum: limit(schema, 'exclusiveMaximum'),
    minItems: limit(schema, 'minItems'),
    maxItems: limit(schema, 'maxItems'),
    uniqueItems: schema.uniqueItems === true,
  };
  for (const name of ['minLength', 'maxLength', 'minItems', 'maxItems'] as const) {
    const value = field[name];
    if (value !== undefined && (!Number.isInteger(value) || value < 0)) throw new Error('Nieprawidłowa długość pola.');
  }
  return field;
}

/** Decode only the declared metadata vocabulary; malformed definitions never grant eligibility. */
export function decodeProviderCatalogue(value: unknown): ProviderCatalogue {
  const result: ProviderCatalogue = { providers: {}, errors: {} };
  try {
    const source = record(value);
    const plugins = record(source.provider_plugins);
    if (
      source.provider_metadata_version !== 2 ||
      !source.provider_plugins ||
      Object.keys(plugins).length > 64 ||
      bytes(plugins) > 1024 * 1024
    )
      throw new Error('Nieobsługiwane lub zbyt duże metadane źródeł.');
    for (const [id, raw] of Object.entries(plugins)) {
      try {
        if (!safeKey(id)) throw new Error('Nieprawidłowy identyfikator źródła.');
        const metadata = record(raw);
        if (!['live', 'synthetic'].includes(String(metadata.data_kind)) || !['http', 'none'].includes(String(metadata.transport_kind)))
          throw new Error('Nieprawidłowy rodzaj źródła.');
        if (has(metadata, 'enabled') || has(metadata, 'legacy_parameter_paths') || has(metadata, 'required_when_enabled'))
          throw new Error('Nieobsługiwany starszy model źródła.');
        const countries = strings(metadata.countries, 256);
        if (countries.some(country => !/^[A-Z]{2}$/.test(country))) throw new Error('Nieprawidłowy kraj.');
        const capability = checkedText(metadata.capability, 128);
        const hazards = strings(metadata.hazards, 5);
        if (
          !capabilities.has(capability) ||
          !hazards.length ||
          hazards.some(hazard => (capability === 'OutdoorAirQuality' ? hazard !== 'outdoor_air_pollution' : !weatherHazards.has(hazard)))
        )
          throw new Error('Nieprawidłowy zakres źródła.');
        const schema = record(metadata.parameter_schema);
        if (
          bytes(schema) > 64 * 1024 ||
          schema.type !== 'object' ||
          schema.additionalProperties !== false ||
          Object.keys(record(schema.properties)).length > 64 ||
          Object.keys(record(schema.$defs)).length > 128
        )
          throw new Error('Nieobsługiwany schemat parametrów.');
        depth(schema);
        const required = strings(schema.required, 64, false);
        const requiredWhenSelected = strings(metadata.required_when_selected, 64);
        const fields: Record<string, ProviderField> = {};
        for (const [name, fieldSchema] of Object.entries(record(schema.properties))) {
          if (!safeKey(name)) throw new Error('Nieprawidłowa nazwa pola.');
          fields[name] = decodeField(fieldSchema, schema, name, required.includes(name));
        }
        if ([...required, ...requiredWhenSelected].some(name => !has(fields, name)))
          throw new Error('Wymagane pole nie jest zadeklarowane.');
        const defaults = record(metadata.parameter_defaults);
        if (Object.keys(defaults).some(name => !has(fields, name))) throw new Error('Nieznane pole domyślne.');
        result.providers[id] = {
          id,
          dataKind: metadata.data_kind as 'live' | 'synthetic',
          transportKind: metadata.transport_kind as 'http' | 'none',
          countries,
          capability,
          hazards,
          displayName: checkedText(metadata.display_name, 256, id),
          description: checkedText(metadata.description, 2048),
          fields,
          requiredWhenSelected,
          defaults: structuredClone(defaults),
        };
      } catch (error) {
        Object.defineProperty(result.errors, id, {
          value: error instanceof Error ? error.message : 'Nieprawidłowe metadane źródła.',
          enumerable: true,
          writable: true,
          configurable: true,
        });
      }
    }
  } catch (error) {
    result.error = error instanceof Error ? error.message : 'Nieprawidłowe metadane źródeł.';
    result.errors._catalogue = result.error;
  }
  return result;
}

/** Project exactly one explicit choice per category without changing the source. */
export function categoryRows(catalogue: ProviderCatalogue, draft: ProviderDraft, country: string): ProviderCategoryRow[] {
  const sources = record(draft.external_sources);
  const normalizedCountry = country.trim().toUpperCase();
  return EXTERNAL_CAPABILITIES.map(capability => {
    const raw = has(sources, capability) ? sources[capability] : undefined;
    const selected = typeof raw === 'string' || raw === null ? raw : undefined;
    const plugin = typeof selected === 'string' && has(catalogue.providers, selected) ? catalogue.providers[selected] : undefined;
    const options = Object.values(catalogue.providers).filter(
      item => item.capability === capability && (!item.countries.length || item.countries.includes(normalizedCountry))
    );
    const error =
      selected === undefined
        ? 'Wybierz źródło lub wyłącz kategorię.'
        : selected === null
          ? undefined
          : !plugin
            ? 'Brak poprawnych metadanych źródła.'
            : plugin.capability !== capability
              ? 'Źródło nie obsługuje tego rodzaju danych.'
              : normalizedCountry && plugin.countries.length && !plugin.countries.includes(normalizedCountry)
                ? 'Źródło nie obsługuje wybranego kraju.'
                : undefined;
    return { capability, label: CATEGORY_LABELS[capability], selected, plugin, options, error };
  });
}

function putPath(draft: ProviderDraft, path: string[], value: unknown): void {
  if (path.some(key => !safeKey(key))) throw new Error('Nieprawidłowa ścieżka pola.');
  let current = draft;
  for (const key of path.slice(0, -1)) {
    current[key] = { ...record(current[key]) };
    current = current[key] as ProviderDraft;
  }
  const final = path[path.length - 1];
  if (value === undefined) delete current[final];
  else current[final] = structuredClone(value);
}
export function setCategoryProvider(draft: ProviderDraft, capability: ExternalCapability, provider: string | null): ProviderDraft {
  if (!EXTERNAL_CAPABILITIES.includes(capability) || (provider !== null && !safeKey(provider)))
    throw new Error('Nieprawidłowy wybór źródła.');
  const result = structuredClone(draft);
  putPath(result, ['external_sources', capability], provider);
  return result;
}
export function readProviderParameters(draft: ProviderDraft, plugin: ProviderDefinition): ProviderDraft {
  const parameters = record(draft.provider_parameters);
  const own = has(parameters, plugin.id) ? record(parameters[plugin.id]) : {};
  return { ...structuredClone(plugin.defaults), ...structuredClone(own) };
}
export function setProviderParameter(draft: ProviderDraft, plugin: ProviderDefinition, name: string, value: unknown): ProviderDraft {
  if (!has(plugin.fields, name)) throw new Error('Nieznany parametr źródła.');
  const result = structuredClone(draft);
  putPath(result, ['provider_parameters', plugin.id, name], value);
  return result;
}

function stringError(value: string, field: Pick<ProviderField, 'minLength' | 'maxLength' | 'pattern'>): string | undefined {
  if (field.minLength !== undefined && value.length < field.minLength) return `Minimalna długość: ${field.minLength}.`;
  if (field.maxLength !== undefined && value.length > field.maxLength) return `Maksymalna długość: ${field.maxLength}.`;
  if (field.pattern && !new RegExp(field.pattern).test(value)) return 'Wartość ma nieprawidłowy format.';
  return undefined;
}
export function providerValueError(value: unknown, field: ProviderField): string | undefined {
  if (value === null) return field.nullable ? undefined : 'Wartość nie może być pusta.';
  if (field.kind === 'boolean') return typeof value === 'boolean' ? undefined : 'Wymagana wartość logiczna.';
  if (field.kind === 'number' || field.kind === 'integer') {
    if (typeof value !== 'number' || !Number.isFinite(value) || (field.kind === 'integer' && !Number.isInteger(value)))
      return 'Wymagana poprawna liczba.';
    if (
      (field.minimum !== undefined && value < field.minimum) ||
      (field.maximum !== undefined && value > field.maximum) ||
      (field.exclusiveMinimum !== undefined && value <= field.exclusiveMinimum) ||
      (field.exclusiveMaximum !== undefined && value >= field.exclusiveMaximum)
    )
      return 'Liczba wykracza poza dozwolony zakres.';
    return undefined;
  }
  if (field.kind === 'string_array') {
    if (!Array.isArray(value) || value.some(item => typeof item !== 'string')) return 'Wymagana lista tekstów.';
    if ((field.minItems !== undefined && value.length < field.minItems) || (field.maxItems !== undefined && value.length > field.maxItems))
      return 'Nieprawidłowa liczba pozycji.';
    if (field.uniqueItems && new Set(value.map(item => item.trim())).size !== value.length) return 'Pozycje nie mogą się powtarzać.';
    for (const item of value) {
      const error = stringError(item, field.item ?? {});
      if (error) return error;
    }
    return undefined;
  }
  if (typeof value !== 'string') return 'Wymagany tekst.';
  if (field.enum && !field.enum.includes(value)) return 'Wybierz dozwoloną wartość.';
  return stringError(value, field);
}
export function validateProviderDraft(catalogue: ProviderCatalogue, draft: ProviderDraft, country: string): ProviderFieldError[] {
  const errors: ProviderFieldError[] = [];
  const add = (path: (string | number)[], code: string, message: string) => errors.push({ path: ['user_config', ...path], code, message });
  const componentEnabled = record(draft.components_enabled).ExternalHazardComponent !== false;
  if (has(draft, 'providers')) add(['providers'], 'obsolete_source', 'Starszy model wyboru źródeł nie jest obsługiwany.');
  if (has(record(record(draft.installation).site), 'teryt_codes'))
    add(['installation', 'site', 'teryt_codes'], 'obsolete_source', 'Parametry regionalne należą do wybranego źródła.');
  if (!draft.external_sources || typeof draft.external_sources !== 'object' || Array.isArray(draft.external_sources)) {
    add(['external_sources'], 'invalid_selection', 'Wybierz źródło lub wyłącz każdą kategorię.');
  }
  const sources = record(draft.external_sources);
  for (const key of Object.keys(sources))
    if (!EXTERNAL_CAPABILITIES.includes(key as ExternalCapability))
      add(['external_sources', key], 'unknown_category', 'Nieznana kategoria źródła.');
  const rows = categoryRows(catalogue, draft, country);
  for (const row of rows) if (row.error) add(['external_sources', row.capability], 'invalid_provider', row.error);
  if (
    draft.provider_parameters !== undefined &&
    (!draft.provider_parameters || typeof draft.provider_parameters !== 'object' || Array.isArray(draft.provider_parameters))
  ) {
    add(['provider_parameters'], 'invalid_parameter', 'Parametry źródeł muszą być obiektem.');
    return errors;
  }
  const parameters = record(draft.provider_parameters);
  const ids = new Set([...Object.keys(parameters), ...rows.flatMap(row => (row.plugin ? [row.plugin.id] : []))]);
  for (const id of ids) {
    const plugin = has(catalogue.providers, id) ? catalogue.providers[id] : undefined;
    if (!plugin) {
      add(['provider_parameters', id], 'unknown_provider', 'Nieznane źródło parametrów.');
      continue;
    }
    const raw = has(parameters, id) ? parameters[id] : {};
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
      add(['provider_parameters', id], 'invalid_parameter', 'Parametry źródła muszą być obiektem.');
      continue;
    }
    const values = readProviderParameters(draft, plugin);
    for (const name of Object.keys(values))
      if (!has(plugin.fields, name)) add(['provider_parameters', id, name], 'unknown_parameter', 'Nieznany parametr źródła.');
    const active = componentEnabled && rows.some(row => row.selected === id && !row.error);
    for (const [name, field] of Object.entries(plugin.fields)) {
      const value = values[name];
      const required = field.required || (active && plugin.requiredWhenSelected.includes(name));
      if (value === undefined || (required && (value === null || value === '' || (Array.isArray(value) && !value.length)))) {
        if (required) add(['provider_parameters', id, name], 'required_when_selected', 'Wypełnij wymagany parametr źródła.');
        continue;
      }
      const message = providerValueError(value, field);
      if (message) add(['provider_parameters', id, name], 'invalid_parameter', message);
    }
  }
  return errors;
}
export function decodeProviderFieldErrors(value: unknown): ProviderFieldError[] {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 32).flatMap(item => {
    const data = record(item);
    if (
      !Array.isArray(data.path) ||
      data.path.length > 16 ||
      data.path.some(
        part => !((typeof part === 'string' && safeKey(part)) || (typeof part === 'number' && Number.isInteger(part) && part >= 0))
      ) ||
      typeof data.message !== 'string' ||
      data.message.length > 512 ||
      typeof data.code !== 'string' ||
      data.code.length > 128
    )
      return [];
    return [{ path: data.path as (string | number)[], code: data.code, message: data.message }];
  });
}
export function providerFieldErrors(errors: ProviderFieldError[], plugin: ProviderDefinition, name: string): ProviderFieldError[] {
  const prefix = ['user_config', 'provider_parameters', plugin.id, name];
  return errors.filter(error => prefix.every((part, index) => error.path[index] === part));
}
