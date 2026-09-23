import { useState } from 'react';
import { initialObject, updateObjectField, type FieldSpec } from './configurationFieldSchemas.js';

type ConfigurationMap = Record<string, unknown>;

interface Props {
  label: string;
  description: string;
  value: ConfigurationMap;
  onChange: (value: ConfigurationMap) => void;
  schema: Record<string, FieldSpec>;
}

function asMap(value: unknown): ConfigurationMap {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as ConfigurationMap) : {};
}

export default function ConfigurationObjectEditor({ label, description, value, onChange, schema }: Props) {
  const [newKey, setNewKey] = useState('');
  const [message, setMessage] = useState('');
  const entries = asMap(value);

  const add = () => {
    const key = newKey.trim();
    if (!/^[A-Z][A-Za-z0-9]*$/.test(key)) {
      setMessage('Wpisz stabilny identyfikator PascalCase, np. LivingRoom.');
      return;
    }
    if (Object.prototype.hasOwnProperty.call(entries, key)) {
      setMessage('Taki identyfikator już istnieje.');
      return;
    }
    onChange({ ...entries, [key]: initialObject(schema) });
    setNewKey('');
    setMessage('');
  };

  return (
    <div className='configuration-object-editor'>
      <div className='configuration-object-heading'>
        <strong>{label}</strong>
        <small>{description}</small>
      </div>
      {Object.entries(entries).map(([key, entry]) => (
        <details className='configuration-object-entry' key={key}>
          <summary>{key}</summary>
          <div className='configuration-object-entry-heading'>
            <small>Ustawienia wpisu {key}</small>
            <button
              className='secondary-button'
              onClick={() => {
                const next = { ...entries };
                delete next[key];
                onChange(next);
              }}
              type='button'
            >
              Usuń wpis
            </button>
          </div>
          <ObjectFields schema={schema} value={asMap(entry)} onChange={next => onChange({ ...entries, [key]: next })} />
        </details>
      ))}
      <div className='configuration-object-add'>
        <label className='configuration-field'>
          <span>Nowy identyfikator</span>
          <input aria-label={`Nowy identyfikator: ${label}`} onChange={event => setNewKey(event.target.value)} value={newKey} />
        </label>
        <button className='secondary-button' onClick={add} type='button'>
          + Dodaj obiekt
        </button>
      </div>
      {message ? <small className='configuration-editor-error'>{message}</small> : null}
    </div>
  );
}

function ObjectFields({
  schema,
  value,
  onChange,
}: {
  schema: Record<string, FieldSpec>;
  value: ConfigurationMap;
  onChange: (value: ConfigurationMap) => void;
}) {
  const [selected, setSelected] = useState('');
  const available = Object.entries(schema).filter(([key]) => {
    if (Object.prototype.hasOwnProperty.call(value, key)) return false;
    if (key === 'gas_identity' && value.hazard !== 'flammable_gas') return false;
    if (key === 'actuator_entity_id' && value.execution_policy !== 'user_confirmed') return false;
    return true;
  });
  const updateField = (key: string, next: unknown) => onChange(updateObjectField(value, key, next));
  return (
    <div className='configuration-nested-fields'>
      {Object.entries(schema)
        .filter(([key]) => key in value)
        .map(([key, field]) => (
          <div className='configuration-nested-row' key={key}>
            <SchemaField field={field} value={value[key]} onChange={next => updateField(key, next)} />
            {!field.required &&
            !(key === 'gas_identity' && value.hazard === 'flammable_gas') &&
            !(key === 'actuator_entity_id' && value.execution_policy === 'user_confirmed') ? (
              <button
                aria-label={`Usuń ustawienie ${field.label}`}
                className='secondary-button'
                onClick={() => {
                  const next = { ...value };
                  delete next[key];
                  onChange(next);
                }}
                type='button'
              >
                Usuń ustawienie
              </button>
            ) : null}
          </div>
        ))}
      {Object.keys(value)
        .filter(key => !(key in schema))
        .map(key => (
          <div className='configuration-nested-row' key={key}>
            <small className='configuration-editor-error'>Nieobsługiwane pole „{key}”.</small>
            <button
              className='secondary-button'
              onClick={() => {
                const next = { ...value };
                delete next[key];
                onChange(next);
              }}
              type='button'
            >
              Usuń nieobsługiwane pole
            </button>
          </div>
        ))}
      {available.length ? (
        <div className='configuration-object-add'>
          <label className='configuration-field'>
            <span>Dodaj ustawienie</span>
            <select aria-label='Wybierz ustawienie' value={selected} onChange={event => setSelected(event.target.value)}>
              <option value=''>Wybierz pole…</option>
              {available.map(([key, field]) => (
                <option key={key} value={key}>
                  {field.label}
                </option>
              ))}
            </select>
          </label>
          <button
            className='secondary-button'
            disabled={!selected}
            onClick={() => {
              const field = schema[selected];
              if (field) updateField(selected, structuredClone(field.initial));
              setSelected('');
            }}
            type='button'
          >
            + Dodaj pole
          </button>
        </div>
      ) : null}
    </div>
  );
}

function SchemaField({ field, value, onChange }: { field: FieldSpec; value: unknown; onChange: (value: unknown) => void }) {
  if (field.kind === 'object') {
    return (
      <fieldset className='configuration-fieldset'>
        <legend title={field.help}>{field.label}</legend>
        <ObjectFields schema={field.fields ?? {}} value={asMap(value)} onChange={onChange} />
      </fieldset>
    );
  }
  if (field.kind === 'list') {
    const entries = Array.isArray(value) ? (value as string[]) : [];
    return (
      <div className='configuration-nested-fields'>
        <strong title={field.help}>{field.label}</strong>
        {field.help ? <small>{field.help}</small> : null}
        {entries.map((entry, index) => (
          <div className='configuration-array-row' key={index}>
            {field.options ? (
              <select
                aria-label={`${field.label} ${index + 1}`}
                value={entry}
                onChange={event => onChange(entries.map((item, position) => (position === index ? event.target.value : item)))}
              >
                <option value=''>Wybierz…</option>
                {field.options.map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            ) : (
              <input
                aria-label={`${field.label} ${index + 1}`}
                value={entry}
                onChange={event => onChange(entries.map((item, position) => (position === index ? event.target.value : item)))}
              />
            )}
            <button
              className='secondary-button'
              onClick={() => onChange(entries.filter((_, position) => position !== index))}
              type='button'
            >
              Usuń
            </button>
          </div>
        ))}
        <button className='secondary-button' onClick={() => onChange([...entries, ''])} type='button'>
          + Dodaj element
        </button>
      </div>
    );
  }
  return (
    <label className='configuration-field'>
      <span title={field.help}>{field.label}</span>
      {field.kind === 'boolean' ? (
        <select value={String(value === true)} onChange={event => onChange(event.target.value === 'true')}>
          <option value='true'>Tak</option>
          <option value='false'>Nie</option>
        </select>
      ) : field.kind === 'select' ? (
        <select value={String(value ?? '')} onChange={event => onChange(event.target.value)}>
          {field.options?.map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
      ) : (
        <input
          type={field.kind === 'number' ? 'number' : 'text'}
          step={field.kind === 'number' ? 'any' : undefined}
          value={String(value ?? '')}
          onChange={event =>
            onChange(field.kind === 'number' ? (event.target.value === '' ? null : Number(event.target.value)) : event.target.value)
          }
        />
      )}
      {field.help ? <small>{field.help}</small> : null}
    </label>
  );
}
