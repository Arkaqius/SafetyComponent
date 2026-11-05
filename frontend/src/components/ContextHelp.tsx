import { useRef, useState } from 'react';
import type { HelpTopic } from '../domain/operatorHelp';
import Icon from './Icon';
import ModalDialog from './ModalDialog';

export function HelpEntries({ topic }: { topic: HelpTopic }) {
  return topic.entries.map(entry => (
    <details className='help-question' key={entry.title}>
      <summary>{entry.title}</summary>
      <p>{entry.text}</p>
    </details>
  ));
}

export default function ContextHelp({ topic }: { topic: HelpTopic }) {
  const [open, setOpen] = useState(false);
  const closeButton = useRef<HTMLButtonElement>(null);

  return (
    <>
      <button
        aria-haspopup='dialog'
        aria-label={`Pomoc dla widoku ${topic.title}`}
        className='text-button context-help-trigger'
        onClick={() => setOpen(true)}
        type='button'
      >
        <Icon name='help' size={17} /> Pomoc
      </button>
      <ModalDialog open={open} onClose={() => setOpen(false)} labelledBy='context-help-title' initialFocus={closeButton}>
        <header className='entity-dialog-header'>
          <h2 id='context-help-title'>Pomoc · {topic.title}</h2>
          <button aria-label='Zamknij pomoc' className='icon-button' onClick={() => setOpen(false)} ref={closeButton} type='button'>
            <Icon name='close' />
          </button>
        </header>
        <div className='entity-dialog-scroll help-page'>
          <p>{topic.intro}</p>
          <HelpEntries topic={topic} />
        </div>
      </ModalDialog>
    </>
  );
}
