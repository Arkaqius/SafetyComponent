export interface FunctionalSafetyDiagnosticsPayload {
  schema_version: 1;
  generated_at: string;
  overall_state: 'observed' | 'attention' | 'unknown';
  diagnostics: Record<string, unknown>;
}

export function parseFunctionalSafetyDiagnostics(value: unknown): FunctionalSafetyDiagnosticsPayload | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  const payload = value as Record<string, unknown>;
  if (payload.schema_version !== 1 || typeof payload.generated_at !== 'string' || !Number.isFinite(Date.parse(payload.generated_at)))
    return null;
  if (payload.overall_state !== 'observed' && payload.overall_state !== 'attention' && payload.overall_state !== 'unknown') return null;
  if (!payload.diagnostics || typeof payload.diagnostics !== 'object' || Array.isArray(payload.diagnostics)) return null;
  return payload as unknown as FunctionalSafetyDiagnosticsPayload;
}

export async function fetchFunctionalSafetyDiagnostics(): Promise<FunctionalSafetyDiagnosticsPayload> {
  const response = await fetch('api/functional-safety', { cache: 'no-store' });
  if (!response.ok) throw new Error(`functional safety diagnostics unavailable: ${response.status}`);
  const payload = parseFunctionalSafetyDiagnostics(await response.json());
  if (!payload) throw new Error('invalid functional safety diagnostics response');
  return payload;
}
