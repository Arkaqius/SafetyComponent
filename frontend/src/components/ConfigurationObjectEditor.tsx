import { useState } from 'react';
type ConfigurationMap = Record<string, unknown>;

type Value = string | number | boolean | null | Value[] | { [key: string]: Value };
const fieldOptions: Record<string, string[]> = {
  kind: ['window', 'door', 'garage_door', 'gate'],
  hazard: ['smoke', 'flammable_gas', 'carbon_monoxide'],
  execution_policy: ['manual', 'user_confirmed'],
  standard: ['european_aqi'],
};

interface Props {
  label: string;
  description: string;
  value: ConfigurationMap;
  onChange: (value: ConfigurationMap) => void;
  newEntry: unknown;
  help?: Record<string, string>;
}

function objectValue(value: unknown): Record<string, Value> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, Value>) : {};
}

function copy(value: Value): Value {
  return structuredClone(value);
}

export default function ConfigurationObjectEditor({ label, description, value, onChange, newEntry, help = {} }: Props) {
  const [newKey, setNewKey] = useState('');
  const [message, setMessage] = useState('');
  const entries = objectValue(value);

  const add = () => {
    const key = newKey.trim();
    if (!key) {
      setMessage('Wpisz identyfikator lub nazwę encji.');
      return;
    }
    if (Object.prototype.hasOwnProperty.call(entries, key)) {
      setMessage('Taki identyfikator już istnieje.');
      return;
    }
    onChange({ ...entries, [key]: copy(newEntry as Value) });
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
        <div className='configuration-object-entry' key={key}>
          <div className='configuration-object-entry-heading'>
            <strong>{key}</strong>
            <button
              className='secondary-button'
              onClick={() => {
                const next = { ...entries };
                delete next[key];
                onChange(next);
              }}
              type='button'
            >
              Usuń
            </button>
          </div>
          <ValueEditor label={key} path={key} value={entry} help={help} onChange={next => onChange({ ...entries, [key]: next })} />
        </div>
      ))}
      <div className='configuration-object-add'>
        <label className='configuration-field'>
          <span>Nowy identyfikator</span>
          <input aria-label={`Nowy identyfikator: ${label}`} onChange={event => setNewKey(event.target.value)} value={newKey} />
        </label>
        <button className='secondary-button' onClick={add} type='button'>
          {typeof newEntry === 'string' ? '+ Dodaj nazwę' : '+ Dodaj obiekt'}
        </button>
      </div>
      {message ? <small className='configuration-editor-error'>{message}</small> : null}
    </div>
  );
}

function ValueEditor({
  label,
  path,
  value,
  onChange,
  help,
}: {
  label: string;
  path: string;
  value: Value;
  onChange: (value: Value) => void;
  help: Record<string, string>;
}) {
  const [newField, setNewField] = useState('');
  const [newType, setNewType] = useState('text');
  const hint = help[path] || help[label];

  if (Array.isArray(value)) {
    return (
      <div className='configuration-nested-fields'>
        <small>
          {label}
          {hint ? ` — ${hint}` : ''}
        </small>
        {value.map((item, index) => (
          <div className='configuration-array-row' key={`${path}-${index}`}>
            <ValueEditor
              label={`${label} ${index + 1}`}
              path={`${path}.${index}`}
              value={item}
              help={help}
              onChange={next => onChange(value.map((current, position) => (position === index ? next : current)))}
            />
            <button className='secondary-button' onClick={() => onChange(value.filter((_, position) => position !== index))} type='button'>
              Usuń
            </button>
          </div>
        ))}
        <button
          className='secondary-button'
          onClick={() => onChange([...value, value.length && typeof value[0] === 'number' ? 0 : ''])}
          type='button'
        >
          + Dodaj element
        </button>
      </div>
    );
  }
  if (value && typeof value === 'object') {
    const fields = objectValue(value);
    return (
      <div className='configuration-nested-fields'>
        {path.includes('.') ? (
          <small>
            {label}
            {hint ? ` — ${hint}` : ''}
          </small>
        ) : null}
        {Object.entries(fields).map(([field, entry]) => (
          <div className='configuration-nested-row' key={field}>
            <ValueEditor
              label={field}
              path={`${path}.${field}`}
              value={entry}
              help={help}
              onChange={next => onChange({ ...fields, [field]: next })}
            />
            <button
              aria-label={`Usuń pole ${field}`}
              className='secondary-button'
              onClick={() => {
                const next = { ...fields };
                delete next[field];
                onChange(next);
              }}
              type='button'
            >
              Usuń pole
            </button>
          </div>
        ))}
        <div className='configuration-object-add'>
          <input
            aria-label={`Nowe pole w ${label}`}
            onChange={event => setNewField(event.target.value)}
            placeholder='Nazwa pola'
            value={newField}
          />
          <select aria-label='Typ pola' onChange={event => setNewType(event.target.value)} value={newType}>
            <option value='text'>Tekst</option>
            <option value='number'>Liczba</option>
            <option value='boolean'>Tak/Nie</option>
            <option value='object'>Obiekt</option>
            <option value='array'>Lista</option>
          </select>
          <button
            className='secondary-button'
            disabled={!newField.trim() || Object.prototype.hasOwnProperty.call(fields, newField.trim())}
            onClick={() => {
              const initial: Value =
                newType === 'number' ? 0 : newType === 'boolean' ? false : newType === 'object' ? {} : newType === 'array' ? [] : '';
              onChange({ ...fields, [newField.trim()]: initial });
              setNewField('');
            }}
            type='button'
          >
            + Dodaj pole
          </button>
        </div>
      </div>
    );
  }
  if (typeof value === 'boolean') {
    return (
      <label className='configuration-field'>
        <span title={hint}>{label}</span>
        <select onChange={event => onChange(event.target.value === 'true')} value={String(value)}>
          <option value='true'>Tak</option>
          <option value='false'>Nie</option>
        </select>
        {hint ? <small>{hint}</small> : null}
      </label>
    );
  }
  if (typeof value === 'string' && fieldOptions[label]) {
    return (
      <label className='configuration-field'>
        <span title={hint}>{label}</span>
        <select onChange={event => onChange(event.target.value)} value={value}>
          {fieldOptions[label].map(option => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
        {hint ? <small>{hint}</small> : null}
      </label>
    );
  }
  return (
    <label className='configuration-field'>
      <span title={hint}>{label}</span>
      <input
        onChange={event => onChange(typeof value === 'number' ? Number(event.target.value) : event.target.value)}
        type={typeof value === 'number' ? 'number' : 'text'}
        step={typeof value === 'number' ? 'any' : undefined}
        value={value ?? ''}
      />
      {hint ? <small>{hint}</small> : null}
    </label>
  );
}
