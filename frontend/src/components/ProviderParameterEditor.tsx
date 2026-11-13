import { useId } from 'react';
import { providerFieldErrors, type ProviderDefinition, type ProviderFieldError } from '../domain/providerConfiguration.js';

interface Props {
  plugin: ProviderDefinition;
  values: Record<string, unknown>;
  active: boolean;
  disabled?: boolean;
  errors?: ProviderFieldError[];
  onChange(name: string, value: unknown): void;
}

/** Render only provider-declared fields; source and activation remain owned by the parent draft. */
export default function ProviderParameterEditor({ plugin, values, active, disabled = false, errors = [], onChange }: Props) {
  const base = useId();
  return <div className='configuration-grid provider-parameters'>
    {Object.entries(plugin.fields).map(([name, field]) => {
      const id = `${base}-${name}`;
      const messages = providerFieldErrors(errors, plugin, name);
      const required = field.required || active && plugin.requiredWhenEnabled.includes(name);
      const value = values[name];
      const common = { id, disabled, 'aria-invalid': messages.length > 0 || undefined, 'aria-describedby': `${id}-help ${id}-error`, 'aria-required': required || undefined };
      return <div className='configuration-field' key={name}>
        <label htmlFor={id}>{field.title}{required ? <span aria-hidden='true'> *</span> : null}</label>
        <small id={`${id}-help`}>{field.description}{required ? ' Wymagane dla włączonego źródła.' : ''}</small>
        {field.kind === 'boolean' ? <input {...common} type='checkbox' checked={value === true} onChange={event => onChange(name, event.target.checked)} /> :
          field.kind === 'enum' ? <select {...common} value={typeof value === 'string' ? value : ''} onChange={event => onChange(name, event.target.value || undefined)}><option value=''>Wybierz…</option>{field.enum?.map(option => <option value={option} key={option}>{option}</option>)}</select> :
          field.kind === 'string_array' ? <textarea {...common} rows={3} value={Array.isArray(value) ? value.join('\n') : ''} onChange={event => onChange(name, event.target.value.split(/\r?\n/).map(item => item.trim()).filter(Boolean))} /> :
          <input {...common} type={field.kind === 'string' ? 'text' : 'number'} value={typeof value === 'string' || typeof value === 'number' ? value : ''} min={field.minimum} max={field.maximum} step={field.kind === 'integer' ? '1' : 'any'} minLength={field.minLength} maxLength={field.maxLength} onChange={event => onChange(name, event.target.value === '' ? undefined : field.kind === 'string' ? event.target.value : Number(event.target.value))} />}
        <div id={`${id}-error`} className='configuration-message-error' role={messages.length ? 'alert' : undefined}>{messages.map((error, index) => <small key={index}>{error.message}</small>)}</div>
      </div>;
    })}
  </div>;
}
