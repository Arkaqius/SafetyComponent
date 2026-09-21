/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_FOLDER_NAME?: string;
  readonly VITE_HA_URL?: string;
  readonly VITE_HA_MOCK?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
