import { useContext, useEffect, useId, useMemo, useRef, useState } from 'react';
import { matchingConfigurationEntities } from '../domain/configurationEntities.js';
import { ConfigurationEntityContext } from './configurationEntityContext.js';

interface Props {
  label: string;
  value: string;
  onChange: (value: string) => void;
  domains?: string[];
  disabled?: boolean;
}

/** Choose an HA binding while retaining manual and temporarily missing IDs. */
export default function EntityInput({ label, value, onChange, domains, disabled = false }: Props) {
  const inventory = useContext(ConfigurationEntityContext);
  const listId = useId();
  const listRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [searching, setSearching] = useState(false);
  const query = searching ? value : '';
  const matches = useMemo(() => matchingConfigurationEntities(inventory, query, domains), [inventory, query, domains]);
  const visible = matches.slice(0, 40);
  const index = Math.min(active, Math.max(0, visible.length - 1));

  useEffect(() => {
    if (open) listRef.current?.children[index]?.scrollIntoView({ block: 'nearest' });
  }, [index, open]);

  const choose = (id: string) => {
    onChange(id);
    setOpen(false);
  };

  return (
    <div className='configuration-entity-picker'>
      <input
        aria-label={label}
        role='combobox'
        aria-autocomplete='list'
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-activedescendant={open && visible.length ? `${listId}-${index}` : undefined}
        autoComplete='off'
        disabled={disabled}
        value={value}
        placeholder='Wyszukaj nazwę lub identyfikator encji…'
        onFocus={() => {
          setOpen(true);
          setSearching(false);
          setActive(0);
        }}
        onBlur={() => setOpen(false)}
        onChange={event => {
          onChange(event.target.value);
          setSearching(true);
          setActive(0);
          setOpen(true);
        }}
        onKeyDown={event => {
          if (event.key === 'Escape') {
            event.preventDefault();
            setOpen(false);
          } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            setOpen(true);
            setActive(current => (open ? Math.max(0, Math.min(visible.length - 1, current + (event.key === 'ArrowDown' ? 1 : -1))) : 0));
          } else if (event.key === 'Enter' && open && visible.length) {
            event.preventDefault();
            choose(visible[index].id);
          }
        }}
      />
      {open ? (
        <div className='configuration-entity-suggestions'>
          <div id={listId} ref={listRef} role='listbox' aria-label={`Encje: ${label}`}>
            {visible.map((option, position) => (
              <button
                id={`${listId}-${position}`}
                key={option.id}
                type='button'
                role='option'
                tabIndex={-1}
                aria-selected={position === index}
                onMouseDown={event => event.preventDefault()}
                onClick={() => choose(option.id)}
              >
                <strong>{option.name}</strong>
                <small>
                  {option.id}
                  {option.unavailable ? ' · brak bieżącego stanu' : ''}
                </small>
              </button>
            ))}
          </div>
          {!visible.length ? <small>Brak podpowiedzi. Możesz wpisać identyfikator ręcznie.</small> : null}
          {matches.length > visible.length ? <small>Wpisz dokładniejszą nazwę, aby zawęzić listę.</small> : null}
        </div>
      ) : null}
    </div>
  );
}
