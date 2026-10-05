import { useEffect, useId, useRef, useState } from 'react';

/** Explanatory help on hover, keyboard focus or tap, without activating the adjacent control. */
export default function HelpTooltip({ label, text }: { label: string; text: string }) {
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLSpanElement>(null);
  const pinned = useRef(false);
  const closeTimer = useRef<number | undefined>(undefined);
  const [open, setOpen] = useState(false);

  const cancelClose = () => window.clearTimeout(closeTimer.current);
  const hide = () => {
    cancelClose();
    pinned.current = false;
    panel.current?.hidePopover();
  };
  const show = () => {
    cancelClose();
    const button = trigger.current;
    const bubble = panel.current;
    if (!button || !bubble) return;
    bubble.style.width = `${Math.min(320, window.innerWidth - 24)}px`;
    bubble.showPopover();
    const anchor = button.getBoundingClientRect();
    const box = bubble.getBoundingClientRect();
    const left = Math.max(12, Math.min(anchor.left, window.innerWidth - box.width - 12));
    const below = anchor.bottom + 8;
    const top = below + box.height <= window.innerHeight - 12 ? below : Math.max(12, anchor.top - box.height - 8);
    bubble.style.left = `${left}px`;
    bubble.style.top = `${top}px`;
  };
  const scheduleClose = () => {
    if (pinned.current || document.activeElement === trigger.current) return;
    cancelClose();
    closeTimer.current = window.setTimeout(hide, 180);
  };

  useEffect(() => {
    const bubble = panel.current;
    const onToggle = (event: Event) => {
      const visible = (event as ToggleEvent).newState === 'open';
      setOpen(visible);
      if (!visible) pinned.current = false;
    };
    bubble?.addEventListener('toggle', onToggle);
    return () => {
      bubble?.removeEventListener('toggle', onToggle);
      window.clearTimeout(closeTimer.current);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const dismiss = (event: Event) => {
      if (event.target instanceof Node && panel.current?.contains(event.target)) return;
      pinned.current = false;
      panel.current?.hidePopover();
    };
    window.addEventListener('resize', dismiss);
    document.addEventListener('scroll', dismiss, true);
    return () => {
      window.removeEventListener('resize', dismiss);
      document.removeEventListener('scroll', dismiss, true);
    };
  }, [open]);

  return (
    <span className='help-tooltip'>
      <button
        aria-label={`Wyjaśnienie: ${label}`}
        aria-describedby={open ? id : undefined}
        aria-controls={id}
        aria-expanded={open}
        className='help-tooltip-trigger'
        ref={trigger}
        type='button'
        onFocus={show}
        onBlur={hide}
        onPointerEnter={event => {
          if (event.pointerType === 'mouse') show();
        }}
        onPointerLeave={scheduleClose}
        onClick={event => {
          event.stopPropagation();
          if (pinned.current) hide();
          else {
            pinned.current = true;
            show();
          }
        }}
      >
        <svg aria-hidden='true' width='18' height='18' viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='1.7'>
          <circle cx='12' cy='12' r='9' />
          <path d='M12 11v6M12 7h.01' />
        </svg>
      </button>
      <span
        className='help-tooltip-panel'
        id={id}
        ref={panel}
        popover='auto'
        role='tooltip'
        onPointerEnter={cancelClose}
        onPointerLeave={scheduleClose}
      >
        <strong>{label}</strong>
        <span>{text}</span>
      </span>
    </span>
  );
}
