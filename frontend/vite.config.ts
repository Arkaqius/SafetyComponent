import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_');
  const folderName = env.VITE_FOLDER_NAME?.trim() || 'SafetyHome';

  if (!/^[A-Za-z0-9_-]+$/.test(folderName)) {
    throw new Error('VITE_FOLDER_NAME może zawierać wyłącznie litery, cyfry, myślnik i podkreślenie.');
  }

  return {
    base: `/local/${folderName}/`,
    plugins: [react()],
  };
});
