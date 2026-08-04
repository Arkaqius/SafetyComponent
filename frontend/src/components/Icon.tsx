export type IconName =
  | 'activity'
  | 'alert'
  | 'chevron'
  | 'close'
  | 'dashboard'
  | 'door'
  | 'environment'
  | 'history'
  | 'menu'
  | 'recovery'
  | 'shield'
  | 'temperature';

interface IconProps {
  name: IconName;
  size?: number;
  className?: string;
}

const paths: Record<IconName, React.ReactNode> = {
  activity: <path d='M3 12h4l2.2-6 4.2 12 2.1-6H21' />,
  alert: (
    <>
      <path d='M12 3 2.8 19a1.2 1.2 0 0 0 1 1.8h16.4a1.2 1.2 0 0 0 1-1.8Z' />
      <path d='M12 9v4' />
      <path d='M12 17h.01' />
    </>
  ),
  chevron: <path d='m9 18 6-6-6-6' />,
  close: (
    <>
      <path d='m6 6 12 12' />
      <path d='M18 6 6 18' />
    </>
  ),
  dashboard: (
    <>
      <rect x='3' y='3' width='7' height='7' rx='1' />
      <rect x='14' y='3' width='7' height='7' rx='1' />
      <rect x='3' y='14' width='7' height='7' rx='1' />
      <rect x='14' y='14' width='7' height='7' rx='1' />
    </>
  ),
  door: (
    <>
      <path d='M5 21h14' />
      <path d='M7 21V4.8A1.8 1.8 0 0 1 8.8 3H17v18' />
      <path d='M10 12h.01' />
    </>
  ),
  environment: (
    <>
      <path d='M4 15.5a4.5 4.5 0 0 1 4.5-4.5h.7A5.5 5.5 0 0 1 20 12.5a3.5 3.5 0 0 1-3.5 3.5H8.5' />
      <path d='M4 19h10' />
      <path d='M6 7h7' />
      <path d='M4 4h4' />
    </>
  ),
  history: (
    <>
      <path d='M3 12a9 9 0 1 0 3-6.7L3 8' />
      <path d='M3 3v5h5' />
      <path d='M12 7v5l3 2' />
    </>
  ),
  menu: (
    <>
      <path d='M4 7h16' />
      <path d='M4 12h16' />
      <path d='M4 17h16' />
    </>
  ),
  recovery: (
    <>
      <circle cx='12' cy='12' r='9' />
      <circle cx='12' cy='12' r='3' />
      <path d='m5.6 5.6 4.3 4.3M14.1 14.1l4.3 4.3M18.4 5.6l-4.3 4.3M9.9 14.1l-4.3 4.3' />
    </>
  ),
  shield: (
    <>
      <path d='M12 3 5 6v5c0 4.6 2.8 8.2 7 10 4.2-1.8 7-5.4 7-10V6Z' />
      <path d='m9 12 2 2 4-4' />
    </>
  ),
  temperature: (
    <>
      <path d='M10 14.8V5a2 2 0 0 1 4 0v9.8a4 4 0 1 1-4 0Z' />
      <path d='M12 9v8' />
    </>
  ),
};

export default function Icon({ name, size = 20, className }: IconProps) {
  return (
    <svg
      aria-hidden='true'
      className={className}
      fill='none'
      height={size}
      viewBox='0 0 24 24'
      width={size}
      xmlns='http://www.w3.org/2000/svg'
    >
      <g stroke='currentColor' strokeLinecap='round' strokeLinejoin='round' strokeWidth='1.8'>
        {paths[name]}
      </g>
    </svg>
  );
}
