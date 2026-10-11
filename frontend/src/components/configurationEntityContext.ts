import { createContext } from 'react';
import type { ConfigurationEntityOption } from '../domain/configurationEntities.js';

export const ConfigurationEntityContext = createContext<ConfigurationEntityOption[]>([]);
