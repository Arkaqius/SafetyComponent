import { typeSync } from '@hakit/core/sync';
import dotenv from 'dotenv';

dotenv.config();

const url = process.env.VITE_HA_URL?.trim();
const token = process.env.HA_SYNC_TOKEN?.trim();

if (!url || !token) {
  console.error('Ustaw VITE_HA_URL i HA_SYNC_TOKEN przed synchronizacją typów.');
  process.exitCode = 1;
} else {
  await typeSync({
    url,
    token,
    outDir: './src',
    filename: 'supported-types.d.ts',
  });
}
