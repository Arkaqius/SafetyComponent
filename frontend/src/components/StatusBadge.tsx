import type { StatusTone } from '../domain/safety';

interface StatusBadgeProps {
  children: React.ReactNode;
  tone?: StatusTone;
  pulse?: boolean;
}

export default function StatusBadge({ children, tone = 'muted', pulse = false }: StatusBadgeProps) {
  return (
    <span className={`status-badge status-${tone}${pulse ? ' status-badge-pulse' : ''}`}>
      <span aria-hidden='true' className='status-dot' />
      {children}
    </span>
  );
}
