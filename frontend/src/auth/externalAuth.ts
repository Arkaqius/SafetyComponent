/** Companion App external-auth bridge types and token acquisition. */

export interface ExternalAuthToken {
  accessToken: string;
  expiresIn: number;
}

export type ExternalAuthResult =
  | { supported: false }
  | { supported: true; token: ExternalAuthToken }
  | { supported: true; error: string };

interface ExternalAuthPayload {
  access_token?: unknown;
  expires_in?: unknown;
}

type ExternalAuthCallback = (success: boolean, payload?: ExternalAuthPayload) => void;

export interface ExternalAuthHost {
  externalAppV2?: {
    postMessage(message: string): void;
  };
  externalApp?: {
    getExternalAuth(options: string): void;
  };
  webkit?: {
    messageHandlers?: {
      getExternalAuth?: {
        postMessage(options: { callback: string; force: boolean }): void;
      };
    };
  };
  externalAuthSetToken?: ExternalAuthCallback;
}

const CALLBACK_NAME = 'externalAuthSetToken';

/**
 * Request the active Home Assistant access token from an Android or iOS
 * Companion App WebView. Returns unsupported in a regular browser.
 */
export async function requestExternalAuthToken(
  host: ExternalAuthHost = window as unknown as ExternalAuthHost,
  { force = false, timeoutMs = 10_000 }: { force?: boolean; timeoutMs?: number } = {}
): Promise<ExternalAuthResult> {
  const hasV2 = typeof host.externalAppV2?.postMessage === 'function';
  const hasV1 = typeof host.externalApp?.getExternalAuth === 'function';
  const hasIos = typeof host.webkit?.messageHandlers?.getExternalAuth?.postMessage === 'function';

  if (!hasV2 && !hasV1 && !hasIos) {
    return { supported: false };
  }

  return new Promise(resolve => {
    const previousCallback = host.externalAuthSetToken;
    let settled = false;

    const finish = (result: ExternalAuthResult) => {
      if (settled) return;
      settled = true;
      globalThis.clearTimeout(timeoutHandle);
      if (previousCallback) {
        host.externalAuthSetToken = previousCallback;
      } else {
        delete host.externalAuthSetToken;
      }
      resolve(result);
    };

    const timeoutHandle = globalThis.setTimeout(
      () => finish({ supported: true, error: 'Companion App nie przekazał tokena autoryzacji.' }),
      timeoutMs
    );

    host.externalAuthSetToken = (success, payload) => {
      const accessToken = typeof payload?.access_token === 'string' ? payload.access_token : '';
      const expiresIn = Number(payload?.expires_in);
      if (!success || !accessToken || !Number.isFinite(expiresIn) || expiresIn <= 0) {
        finish({ supported: true, error: 'Companion App zwrócił nieprawidłowy token autoryzacji.' });
        return;
      }
      finish({
        supported: true,
        token: {
          accessToken,
          expiresIn,
        },
      });
    };

    const options = { callback: CALLBACK_NAME, force };
    try {
      if (hasV2) {
        host.externalAppV2!.postMessage(
          JSON.stringify({
            type: 'getExternalAuth',
            payload: options,
          })
        );
      } else if (hasV1) {
        host.externalApp!.getExternalAuth(JSON.stringify(options));
      } else {
        host.webkit!.messageHandlers!.getExternalAuth!.postMessage(options);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      finish({ supported: true, error: `Nie udało się pobrać tokena Companion App: ${message}` });
    }
  });
}
