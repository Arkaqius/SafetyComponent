/** Typed, bounded provider metadata and immutable installation-draft operations. */
export type ProviderDraft = Record<string, unknown>;
export type ProviderIntent = 'inherit' | 'enabled' | 'disabled';
export interface ProviderFieldError { path: (string | number)[]; code: string; message: string }
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
  enabled: boolean;
  countries: string[];
  capability: string;
  hazards: string[];
  displayName: string;
  description: string;
  fields: Record<string, ProviderField>;
  requiredWhenEnabled: string[];
  defaults: ProviderDraft;
  legacyPaths: Record<string, string[]>;
}
export interface ProviderCatalogue { providers: Record<string, ProviderDefinition>; errors: Record<string, string>; error?: string }
export interface ProviderRow { id: string; plugin?: ProviderDefinition; intent: ProviderIntent; applicable: boolean; effectiveEnabled: boolean; error?: string }

const forbiddenKeys = new Set(['__proto__', 'constructor', 'prototype']);
const capabilities = new Set(['WeatherPointModel', 'OfficialWeatherWarnings', 'OutdoorAirQuality']);
const weatherHazards = new Set(['frost', 'wind', 'rain', 'storm']);
const bytes = (value: unknown) => new TextEncoder().encode(JSON.stringify(value)).length;
const has = (value: object, key: string) => Object.prototype.hasOwnProperty.call(value, key);
const record = (value: unknown): ProviderDraft => value !== null && typeof value === 'object' && !Array.isArray(value) ? value as ProviderDraft : {};
function safeKey(value: string): boolean { return value.length > 0 && value.length <= 128 && !forbiddenKeys.has(value); }
function checkedText(value: unknown, limit: number, fallback = ''): string {
  if (value === undefined) return fallback;
  if (typeof value !== 'string' || value.length > limit) throw new Error('Nieprawidłowy tekst metadanych.');
  return value;
}
function strings(value: unknown, limit: number, required = true): string[] {
  if (value === undefined && !required) return [];
  if (!Array.isArray(value) || value.length > limit || value.some(item => typeof item !== 'string' || !safeKey(item))) throw new Error('Nieprawidłowa lista metadanych.');
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
    if (!reference.startsWith('#/$defs/') || refs.includes(reference) || refs.length >= 16) throw new Error('Nieobsługiwane odwołanie schematu.');
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
    if (type !== 'string' || !Array.isArray(schema.enum) || schema.enum.length > 1024 || !schema.enum.length) throw new Error('Nieprawidłowe opcje pola.');
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
    kind, title: checkedText(schema.title, 256, name), description: checkedText(schema.description, 2048), nullable, required,
    default: schema.default, enum: options, item,
    minLength: limit(schema, 'minLength'), maxLength: limit(schema, 'maxLength'), pattern: pattern(schema.pattern),
    minimum: limit(schema, 'minimum'), maximum: limit(schema, 'maximum'), exclusiveMinimum: limit(schema, 'exclusiveMinimum'), exclusiveMaximum: limit(schema, 'exclusiveMaximum'),
    minItems: limit(schema, 'minItems'), maxItems: limit(schema, 'maxItems'), uniqueItems: schema.uniqueItems === true,
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
    if (source.provider_metadata_version !== 1 || !source.provider_plugins || Object.keys(plugins).length > 64 || bytes(plugins) > 1024 * 1024) throw new Error('Nieobsługiwane lub zbyt duże metadane źródeł.');
    for (const [id, raw] of Object.entries(plugins)) {
      try {
        if (!safeKey(id)) throw new Error('Nieprawidłowy identyfikator źródła.');
        const metadata = record(raw);
        if (typeof metadata.enabled !== 'boolean') throw new Error('Brak domyślnego włączenia.');
        const countries = strings(metadata.countries, 256);
        if (countries.some(country => !/^[A-Z]{2}$/.test(country))) throw new Error('Nieprawidłowy kraj.');
        const capability = checkedText(metadata.capability, 128);
        const hazards = strings(metadata.hazards, 5);
        if (!capabilities.has(capability) || !hazards.length || hazards.some(hazard => capability === 'OutdoorAirQuality' ? hazard !== 'outdoor_air_pollution' : !weatherHazards.has(hazard))) throw new Error('Nieprawidłowy zakres źródła.');
        const schema = record(metadata.parameter_schema);
        if (bytes(schema) > 64 * 1024 || schema.type !== 'object' || schema.additionalProperties !== false || Object.keys(record(schema.properties)).length > 64 || Object.keys(record(schema.$defs)).length > 128) throw new Error('Nieobsługiwany schemat parametrów.');
        depth(schema);
        const required = strings(schema.required, 64, false);
        const requiredWhenEnabled = strings(metadata.required_when_enabled, 64);
        const fields: Record<string, ProviderField> = {};
        for (const [name, fieldSchema] of Object.entries(record(schema.properties))) {
          if (!safeKey(name)) throw new Error('Nieprawidłowa nazwa pola.');
          fields[name] = decodeField(fieldSchema, schema, name, required.includes(name));
        }
        if ([...required, ...requiredWhenEnabled].some(name => !has(fields, name))) throw new Error('Wymagane pole nie jest zadeklarowane.');
        const legacyPaths: Record<string, string[]> = {};
        for (const [name, rawPath] of Object.entries(record(metadata.legacy_parameter_paths))) {
          const path = strings(rawPath, 16);
          if (!has(fields, name) || path.length < 2 || path[0] !== 'installation') throw new Error('Nieprawidłowa ścieżka zgodności.');
          legacyPaths[name] = path;
        }
        const defaults = record(metadata.parameter_defaults);
        if (Object.keys(defaults).some(name => !has(fields, name))) throw new Error('Nieznane pole domyślne.');
        result.providers[id] = {
          id, enabled: metadata.enabled, countries, capability, hazards,
          displayName: checkedText(metadata.display_name, 256, id), description: checkedText(metadata.description, 2048),
          fields, requiredWhenEnabled, defaults: structuredClone(defaults), legacyPaths,
        };
      } catch (error) { result.errors[id] = error instanceof Error ? error.message : 'Nieprawidłowe metadane źródła.'; }
    }
  } catch (error) {
    result.error = error instanceof Error ? error.message : 'Nieprawidłowe metadane źródeł.';
    result.errors._catalogue = result.error;
  }
  return result;
}

export function providerRows(catalogue: ProviderCatalogue, draft: ProviderDraft, country: string): ProviderRow[] {
  const choices = record(draft.providers);
  const ids = new Set([...Object.keys(catalogue.providers), ...Object.keys(choices), ...Object.keys(catalogue.errors).filter(id => id !== '_catalogue')]);
  return [...ids].filter(id => {
    const plugin = catalogue.providers[id];
    return has(choices, id) || !plugin || !plugin.countries.length || plugin.countries.includes(country);
  }).map(id => {
    const plugin = catalogue.providers[id];
    const selection = record(choices[id]);
    const intent: ProviderIntent = selection.enabled === true ? 'enabled' : selection.enabled === false ? 'disabled' : 'inherit';
    const applicable = Boolean(plugin && (!plugin.countries.length || plugin.countries.includes(country)));
    const error = !plugin ? 'Brak poprawnych metadanych źródła.' : has(selection, 'enabled') && typeof selection.enabled !== 'boolean' ? 'Włączenie źródła musi być wartością logiczną.' : intent === 'enabled' && !applicable ? 'Źródło nie obsługuje wybranego kraju.' : undefined;
    return { id, plugin, intent, applicable, error, effectiveEnabled: Boolean(plugin && applicable && !error && (intent === 'enabled' || intent === 'inherit' && plugin.enabled)) };
  });
}

function getPath(draft: ProviderDraft, path: string[]): unknown {
  return path.reduce<unknown>((value, key) => record(value)[key], draft);
}
function putPath(draft: ProviderDraft, path: string[], value: unknown): void {
  if (path.some(key => !safeKey(key))) throw new Error('Nieprawidłowa ścieżka pola.');
  let current = draft;
  for (const key of path.slice(0, -1)) { current[key] = { ...record(current[key]) }; current = current[key] as ProviderDraft; }
  const final = path[path.length - 1];
  if (value === undefined) delete current[final]; else current[final] = structuredClone(value);
}
function equivalent(left: unknown, right: unknown): boolean {
  const normalize = (value: unknown) => Array.isArray(value) && value.every(item => typeof item === 'string') ? [...value].map(item => item.trim()).sort() : value;
  return JSON.stringify(normalize(left)) === JSON.stringify(normalize(right));
}
export function setProviderIntent(draft: ProviderDraft, id: string, intent: ProviderIntent): ProviderDraft {
  const result = structuredClone(draft);
  putPath(result, ['providers', id, 'enabled'], intent === 'inherit' ? undefined : intent === 'enabled');
  const providers = record(result.providers);
  if (Object.keys(record(providers[id])).length === 0) delete providers[id];
  return result;
}
export function removeProviderSelection(draft: ProviderDraft, id: string): ProviderDraft {
  const result = structuredClone(draft);
  if (safeKey(id)) delete record(result.providers)[id];
  return result;
}
export function readProviderParameters(draft: ProviderDraft, plugin: ProviderDefinition): { values: ProviderDraft; conflicts: Record<string, { canonical: unknown; legacy: unknown }> } {
  const canonical = record(record(record(draft.providers)[plugin.id]).parameters);
  const values = { ...structuredClone(plugin.defaults), ...structuredClone(canonical) };
  const conflicts: Record<string, { canonical: unknown; legacy: unknown }> = {};
  for (const [name, path] of Object.entries(plugin.legacyPaths)) {
    const legacy = getPath(draft, path);
    if (legacy === undefined) continue;
    if (has(canonical, name) && !equivalent(canonical[name], legacy)) conflicts[name] = { canonical: canonical[name], legacy };
    if (!has(canonical, name)) values[name] = structuredClone(legacy);
  }
  return { values, conflicts };
}
export function setProviderParameter(draft: ProviderDraft, plugin: ProviderDefinition, name: string, value: unknown): ProviderDraft {
  if (!has(plugin.fields, name)) throw new Error('Nieznany parametr źródła.');
  if (readProviderParameters(draft, plugin).conflicts[name]) throw new Error('Najpierw uzgodnij sprzeczne wartości parametru.');
  const result = structuredClone(draft);
  const alias = plugin.legacyPaths[name];
  const legacyPresent = alias && getPath(draft, alias) !== undefined;
  const canonicalPresent = has(record(record(record(draft.providers)[plugin.id]).parameters), name);
  if (legacyPresent) putPath(result, alias, value);
  if (canonicalPresent || !legacyPresent) putPath(result, ['providers', plugin.id, 'parameters', name], value);
  return result;
}
export function reconcileProviderParameter(draft: ProviderDraft, plugin: ProviderDefinition, name: string, choice: 'canonical' | 'legacy'): ProviderDraft {
  const conflict = readProviderParameters(draft, plugin).conflicts[name];
  if (!conflict) return structuredClone(draft);
  const result = structuredClone(draft);
  putPath(result, ['providers', plugin.id, 'parameters', name], conflict[choice]);
  putPath(result, plugin.legacyPaths[name], conflict[choice]);
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
    if (typeof value !== 'number' || !Number.isFinite(value) || field.kind === 'integer' && !Number.isInteger(value)) return 'Wymagana poprawna liczba.';
    if (field.minimum !== undefined && value < field.minimum || field.maximum !== undefined && value > field.maximum || field.exclusiveMinimum !== undefined && value <= field.exclusiveMinimum || field.exclusiveMaximum !== undefined && value >= field.exclusiveMaximum) return 'Liczba wykracza poza dozwolony zakres.';
    return undefined;
  }
  if (field.kind === 'string_array') {
    if (!Array.isArray(value) || value.some(item => typeof item !== 'string')) return 'Wymagana lista tekstów.';
    if (field.minItems !== undefined && value.length < field.minItems || field.maxItems !== undefined && value.length > field.maxItems) return 'Nieprawidłowa liczba pozycji.';
    if (field.uniqueItems && new Set(value.map(item => item.trim())).size !== value.length) return 'Pozycje nie mogą się powtarzać.';
    for (const item of value) { const error = stringError(item, field.item ?? {}); if (error) return error; }
    return undefined;
  }
  if (typeof value !== 'string') return 'Wymagany tekst.';
  if (field.enum && !field.enum.includes(value)) return 'Wybierz dozwoloną wartość.';
  return stringError(value, field);
}
export function validateProviderDraft(catalogue: ProviderCatalogue, draft: ProviderDraft, country: string): ProviderFieldError[] {
  const errors: ProviderFieldError[] = [];
  const componentEnabled = record(draft.components_enabled).ExternalHazardComponent !== false;
  for (const row of providerRows(catalogue, draft, country)) {
    const prefix = ['user_config', 'providers', row.id];
    if (row.error) { errors.push({ path: prefix, code: 'invalid_provider', message: row.error }); if (!row.plugin) continue; }
    const plugin = row.plugin;
    if (!plugin) continue;
    const { values, conflicts } = readProviderParameters(draft, plugin);
    for (const name of Object.keys(values)) {
      if (!has(plugin.fields, name)) errors.push({ path: [...prefix, 'parameters', name], code: 'unknown_parameter', message: 'Nieznany parametr źródła.' });
    }
    for (const [name, field] of Object.entries(plugin.fields)) {
      const path = [...prefix, 'parameters', name];
      if (conflicts[name]) { errors.push({ path, code: 'alias_conflict', message: 'Uzgodnij sprzeczne wartości parametru.' }); continue; }
      const value = values[name];
      const required = field.required || componentEnabled && row.effectiveEnabled && plugin.requiredWhenEnabled.includes(name);
      if (value === undefined || value === null && required) { if (required) errors.push({ path, code: 'required_when_enabled', message: 'Wypełnij wymagany parametr źródła.' }); continue; }
      const message = providerValueError(value, field);
      if (message) errors.push({ path, code: 'invalid_parameter', message });
    }
  }
  return errors;
}
export function decodeProviderFieldErrors(value: unknown): ProviderFieldError[] {
  if (!Array.isArray(value)) return [];
  return value.slice(0, 32).flatMap(item => {
    const data = record(item);
    if (!Array.isArray(data.path) || data.path.length > 16 || data.path.some(part => !(typeof part === 'string' && safeKey(part) || typeof part === 'number' && Number.isInteger(part) && part >= 0)) || typeof data.message !== 'string' || data.message.length > 512 || typeof data.code !== 'string' || data.code.length > 128) return [];
    return [{ path: data.path as (string | number)[], code: data.code, message: data.message }];
  });
}
export function providerFieldErrors(errors: ProviderFieldError[], plugin: ProviderDefinition, name: string): ProviderFieldError[] {
  const canonical = ['user_config', 'providers', plugin.id, 'parameters', name];
  const legacy = plugin.legacyPaths[name] ? ['user_config', ...plugin.legacyPaths[name]] : [];
  return errors.filter(error => [canonical, legacy].some(prefix => prefix.length > 0 && prefix.every((part, index) => error.path[index] === part)));
}
