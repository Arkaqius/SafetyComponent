import type { IconName } from './Icon';
import Icon from './Icon';
import type { StatusTone } from '../domain/safety';
import HelpTooltip from './HelpTooltip';

interface SummaryCardProps {
  label: string;
  value: string | number;
  detail: string;
  icon: IconName;
  tone?: StatusTone;
  onClick?: () => void;
  help?: string;
}

export default function SummaryCard({ label, value, detail, icon, tone = 'info', onClick, help }: SummaryCardProps) {
  const content = (
    <>
      <div className='summary-card-icon'>
        <Icon name={icon} size={22} />
      </div>
      <div className='summary-card-body'>
        <span className='summary-card-label'>{label}</span>
        <strong className='summary-card-value'>{value}</strong>
        <span className='summary-card-detail'>{detail}</span>
      </div>
    </>
  );

  const card = onClick ? (
    <button className={`summary-card summary-card-clickable summary-${tone}`} onClick={onClick} type='button'>
      {content}
    </button>
  ) : (
    <article className={`summary-card summary-${tone}`}>{content}</article>
  );
  return help ? (
    <div className='summary-card-with-help'>
      {card}
      <HelpTooltip label={label} text={help} />
    </div>
  ) : (
    card
  );
}
