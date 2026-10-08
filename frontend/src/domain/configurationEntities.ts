import type { EntityMap } from './safety.js';

export interface ConfigurationEntityOption {
  id: string;
  name: string;
  unavailable: boolean;
}

/** Reuse the HA startup inventory without removing unavailable bindings. */
export function configurationEntityOptions(entities: EntityMap): ConfigurationEntityOption[] {
  return Object.entries(entities)
    .map(([id, entity]) => ({
      id,
      name: typeof entity.attributes.friendly_name === 'string' ? entity.attributes.friendly_name : id,
      unavailable: ['unavailable', 'unknown'].includes(entity.state),
    }))
    .sort((a, b) => a.name.localeCompare(b.name, 'pl') || a.id.localeCompare(b.id));
}

/** Search both the operator name and stable ID, within the field's domains. */
export function matchingConfigurationEntities(options: ConfigurationEntityOption[], query: string, domains: string[] = []) {
  const terms = query.trim().toLocaleLowerCase('pl').split(/\s+/).filter(Boolean);
  return options.filter(option => {
    const domain = option.id.split('.')[0];
    const text = `${option.name} ${option.id}`.toLocaleLowerCase('pl');
    return (!domains.length || domains.includes(domain)) && terms.every(term => text.includes(term));
  });
}
