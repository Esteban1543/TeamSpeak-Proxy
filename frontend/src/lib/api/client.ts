/**
 * Facade: único punto de comunicación con el backend.
 * Serializa JSON, normaliza errores y redirige a /login ante un 401.
 */

const BASE_URL = (import.meta.env.PUBLIC_API_URL ?? '/api').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  /** Si es false, un 401 se devuelve como ApiError en vez de redirigir a /login. */
  redirectOn401?: boolean;
}

function goToLogin(): void {
  if (!location.pathname.startsWith('/login')) {
    location.replace('/login');
  }
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, redirectOn401 = true } = options;
  const init: RequestInit = {
    method,
    credentials: 'same-origin',
    headers: { Accept: 'application/json' },
  };
  if (body !== undefined) {
    init.headers = { ...init.headers, 'Content-Type': 'application/json' };
    init.body = JSON.stringify(body);
  }

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, init);
  } catch {
    throw new ApiError('No se pudo conectar con el servidor', 0);
  }

  if (response.status === 401 && redirectOn401) {
    goToLogin();
    throw new ApiError('Sesión caducada', 401);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(extractMessage(data, response.status), response.status, extractCode(data));
  }
  return data as T;
}

function extractMessage(data: unknown, status: number): string {
  if (data && typeof data === 'object' && 'detail' in data) {
    const detail = (data as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    // Errores de validación de FastAPI: lista de { msg }
    if (Array.isArray(detail) && detail[0] && typeof detail[0].msg === 'string') return detail[0].msg;
  }
  return `Error inesperado del servidor (${status})`;
}

function extractCode(data: unknown): string | undefined {
  if (data && typeof data === 'object' && 'code' in data) {
    const code = (data as { code: unknown }).code;
    return typeof code === 'string' ? code : undefined;
  }
  return undefined;
}
