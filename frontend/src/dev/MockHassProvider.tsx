import { type ReactNode } from 'react';
import { HassContext, type HassContextProps, type Store } from '@hakit/core';
import { MOCK_ENTITIES, MOCK_STARTED_AT } from './mockData';

const noChange = (): void => undefined;
const mockStore = {
  entities: MOCK_ENTITIES,
  setEntities: noChange,
  connection: null,
  setConnection: noChange,
  error: null,
  setError: noChange,
  cannotConnect: false,
  setCannotConnect: noChange,
  ready: true,
  setReady: noChange,
  lastUpdated: new Date(MOCK_STARTED_AT),
  setLastUpdated: noChange,
  hash: '',
  setHash: noChange,
  routes: [],
  setRoutes: noChange,
  auth: null,
  setAuth: noChange,
  config: null,
  setConfig: noChange,
  hassUrl: 'mock://home-assistant',
  setHassUrl: noChange,
  breakpoints: {
    xxs: 0,
    xs: 320,
    sm: 640,
    md: 768,
    lg: 1024,
    xlg: 1280,
  },
  setBreakpoints: noChange,
  setGlobalComponentStyles: noChange,
  globalComponentStyles: {},
  setPortalRoot: noChange,
  locales: null,
  setLocales: noChange,
} as unknown as Store;

const useMockStore = (<T,>(selector: (state: Store) => T): T => selector(mockStore)) as HassContextProps['useStore'];

const mockContext = {
  useStore: useMockStore,
  logout: noChange,
  getStates: async () => Object.values(MOCK_ENTITIES) as Awaited<ReturnType<HassContextProps['getStates']>>,
  getServices: async () => null,
  getConfig: async () => null,
  getUser: async () => null,
  callService: noChange,
  addRoute: noChange,
  getRoute: () => null,
  getAllEntities: () => MOCK_ENTITIES as ReturnType<HassContextProps['getAllEntities']>,
  joinHassUrl: (path: string) => path,
  callApi: async () => ({
    data: 'Tryb demonstracyjny nie wykonuje zapytań API.',
    status: 'error' as const,
  }),
} as HassContextProps;

/**
 * Provides deterministic SafetyComponent data for local visual development.
 * It is only selected when Vite runs in development mode with VITE_HA_MOCK=true.
 */
export default function MockHassProvider({ children }: { children: ReactNode }) {
  return <HassContext.Provider value={mockContext}>{children}</HassContext.Provider>;
}
