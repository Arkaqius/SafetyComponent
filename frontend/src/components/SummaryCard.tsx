import type { IconName } from './Icon';
import Icon from './Icon';
import type { StatusTone } from '../domain/safety';

interface SummaryCardProps {
  label: string;
  value: string | number;
  detail: string;
  icon: IconName;
  tone?: StatusTone;
}

export default function SummaryCard({ label, value, detail, icon, tone = 'info' }: SummaryCardProps) {
  return (
    <article className={`summary-card summary-${tone}`}>
      <div className='summary-card-icon'>
        <Icon name={icon} size={22} />
      </div>
      <div className='summary-card-body'>
        <span className='summary-card-label'>{label}</span>
        <strong className='summary-card-value'>{value}</strong>
        <span className='summary-card-detail'>{detail}</span>
      </div>
    </article>
  );
}
