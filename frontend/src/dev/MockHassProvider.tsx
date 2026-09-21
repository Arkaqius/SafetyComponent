import { type ReactNode } from 'react';
import { useHass, type Store } from '@hakit/core';
import { MOCK_ENTITIES } from './mockData';

const mockStore = {
  entities: MOCK_ENTITIES as unknown as Store['entities'],
  connection: null,
  connectionStatus: 'connected',
  ready: true,
  hassUrl: 'mock://home-assistant',
} satisfies Partial<Store>;

useHass.setState(mockStore);

/**
 * Provides deterministic SafetyComponent data for local visual development.
 * It is only selected when Vite runs in development mode with VITE_HA_MOCK=true.
 */
export default function MockHassProvider({ children }: { children: ReactNode }) {
  return children;
}
