import { useEffect, useRef, type ReactNode, type RefObject } from 'react';

/** Native modal lifecycle keeps the background inert and the close callback current. */
export default function ModalDialog({
  open,
  onClose,
  labelledBy,
  initialFocus,
  children,
}: {
  open: boolean;
  onClose: () => void;
  labelledBy: string;
  initialFocus: RefObject<HTMLButtonElement | null>;
  children: ReactNode;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const closeRef = useRef(onClose);
  useEffect(() => {
    closeRef.current = onClose;
  }, [onClose]);
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!open || !dialog) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    dialog.showModal();
    initialFocus.current?.focus();
    const cancel = (event: Event) => {
      event.preventDefault();
      closeRef.current();
    };
    const trapFocus = (event: KeyboardEvent) => {
      if (event.key !== 'Tab') return;
      const controls = Array.from(
        dialog.querySelectorAll<HTMLElement>('button, a[href], input, select, textarea, summary, [tabindex]:not([tabindex="-1"])')
      ).filter(element => !element.hasAttribute('disabled') && element.getClientRects().length > 0);
      const first = controls[0];
      const last = controls.at(-1);
      if (!first || !last) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) {
        event.preventDefault();
        first.focus();
      }
    };
    dialog.addEventListener('cancel', cancel);
    dialog.addEventListener('keydown', trapFocus);
    return () => {
      dialog.removeEventListener('cancel', cancel);
      dialog.removeEventListener('keydown', trapFocus);
      dialog.close();
      document.body.style.overflow = previousOverflow;
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, [initialFocus, open]);
  if (!open) return null;
  return (
    <dialog
      aria-labelledby={labelledBy}
      aria-modal='true'
      className='entity-dialog-backdrop'
      ref={dialogRef}
      onMouseDown={event => {
        if (event.target === event.currentTarget) closeRef.current();
      }}
    >
      <section className='entity-dialog'>{children}</section>
    </dialog>
  );
}
