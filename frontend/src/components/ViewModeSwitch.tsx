export type ViewMode = 'basic' | 'advanced';

export const VIEW_MODE_STORAGE_KEY = 'safetyhome.view-mode';

export interface ViewModeContext {
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
}

export default function ViewModeSwitch({ viewMode, onViewModeChange }: ViewModeContext) {
  return (
    <div aria-label='Widok aplikacji' className='view-mode-switch' role='group'>
      <button aria-pressed={viewMode === 'basic'} onClick={() => onViewModeChange('basic')} type='button'>
        Podstawowy
      </button>
      <button aria-pressed={viewMode === 'advanced'} onClick={() => onViewModeChange('advanced')} type='button'>
        Rozszerzony
      </button>
    </div>
  );
}
