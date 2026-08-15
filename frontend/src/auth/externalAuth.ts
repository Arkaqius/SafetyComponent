/** Companion App external-auth bridge types and token acquisition. */

export interface ExternalAuthToken {
  accessToken: string;
  expiresIn: number;
}

export type ExternalAuthResult = { supported: false } | { supported: true; token: ExternalAuthToken } | { supported: true; error: string };

interface ExternalAuthPayload {
  access_token?: unknown;
  expires_in?: unknown;
}

type ExternalAuthCallback = (success: boolean, payload?: ExternalAuthPayload) => void;
type ExternalAuthOptions = { callback: string; force?: boolean };

export interface ExternalAuthHost {
  top?: ExternalAuthHost | null;
  externalAppV2?: {
    postMessage(message: string): void;
  };
  externalApp?: {
    getExternalAuth(options: string): void;
  };
  webkit?: {
    messageHandlers?: {
      getExternalAuth?: {
        postMessage(options: ExternalAuthOptions): void;
      };
    };
  };
  externalAuthSetToken?: ExternalAuthCallback;
}

const CALLBACK_NAME = 'externalAuthSetToken';

function supportsExternalAuth(host: ExternalAuthHost): boolean {
  return (
    typeof host.externalAppV2?.postMessage === 'function' ||
    typeof host.externalApp?.getExternalAuth === 'function' ||
    typeof host.webkit?.messageHandlers?.getExternalAuth?.postMessage === 'function'
  );
}

/**
 * Resolve the frame that owns the Companion App bridge. Webpage dashboards
 * render applications in an iframe, while Android invokes auth callbacks in
 * the main WebView frame.
 */
export function resolveExternalAuthHost(host: ExternalAuthHost): ExternalAuthHost {
  try {
    const topHost = host.top;
    if (topHost && topHost !== host && supportsExternalAuth(topHost)) {
      return topHost;
    }
  } catch {
    // Cross-origin iframe: the main frame cannot be accessed safely.
  }
  return host;
}

/**
 * Request the active Home Assistant access token from an Android or iOS
 * Companion App WebView. Returns unsupported in a regular browser.
 */
export async function requestExternalAuthToken(
  host: ExternalAuthHost = resolveExternalAuthHost(window as unknown as ExternalAuthHost),
  { force = false, timeoutMs = 30_000 }: { force?: boolean; timeoutMs?: number } = {}
): Promise<ExternalAuthResult> {
  const authHost = resolveExternalAuthHost(host);
  const hasV2 = typeof authHost.externalAppV2?.postMessage === 'function';
  const hasV1 = typeof authHost.externalApp?.getExternalAuth === 'function';
  const hasIos = typeof authHost.webkit?.messageHandlers?.getExternalAuth?.postMessage === 'function';

  if (!hasV2 && !hasV1 && !hasIos) {
    return { supported: false };
  }

  return new Promise(resolve => {
    const previousCallback = authHost.externalAuthSetToken;
    let settled = false;

    const finish = (result: ExternalAuthResult) => {
      if (settled) return;
      settled = true;
      globalThis.clearTimeout(timeoutHandle);
      if (previousCallback) {
        authHost.externalAuthSetToken = previousCallback;
      } else {
        delete authHost.externalAuthSetToken;
      }
      resolve(result);
    };

    const timeoutHandle = globalThis.setTimeout(
      () => finish({ supported: true, error: 'Companion App nie przekazał tokena autoryzacji.' }),
      timeoutMs
    );

    authHost.externalAuthSetToken = (success, payload) => {
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

    const options: ExternalAuthOptions = { callback: CALLBACK_NAME };
    if (force) options.force = true;

    void Promise.resolve().then(() => {
      try {
        if (hasV2) {
          authHost.externalAppV2!.postMessage(
            JSON.stringify({
              type: 'getExternalAuth',
              payload: options,
            })
          );
        } else if (hasV1) {
          authHost.externalApp!.getExternalAuth(JSON.stringify(options));
        } else {
          authHost.webkit!.messageHandlers!.getExternalAuth!.postMessage(options);
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        finish({ supported: true, error: `Nie udało się pobrać tokena Companion App: ${message}` });
      }
    });
  });
}
