/**
 * Estado compartido (Observer con nanostores): los componentes se suscriben y
 * se actualizan solos cuando se crea o elimina una redirección.
 */
import { atom } from 'nanostores';
import { ApiError } from './api/client';
import { createRedirect, deleteRedirect, getPortUsage, listRedirects, updateRedirectAlias } from './api/redirects';
import type { PortUsage, Redirect } from '../types/redirect';

export type ToastKind = 'success' | 'error' | 'info';
export interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

export const $redirects = atom<Redirect[]>([]);
export const $portUsage = atom<PortUsage | null>(null);
export const $loaded = atom(false);
export const $lastUpdated = atom<Date | null>(null);
export const $toasts = atom<Toast[]>([]);

const POLL_MS = 5_000;
let toastSeq = 0;
let polling = false;

export function toast(message: string, kind: ToastKind = 'info', ttl = 5000): void {
  const item: Toast = { id: ++toastSeq, kind, message };
  $toasts.set([...$toasts.get(), item]);
  setTimeout(() => dismissToast(item.id), ttl);
}

export function dismissToast(id: number): void {
  $toasts.set($toasts.get().filter((t) => t.id !== id));
}

export function errorMessage(err: unknown): string {
  return err instanceof ApiError || err instanceof Error ? err.message : 'Error desconocido';
}

export async function refreshUsage(): Promise<void> {
  $portUsage.set(await getPortUsage());
}

export async function refresh(): Promise<void> {
  const [redirects, usage] = await Promise.all([listRedirects(), getPortUsage()]);
  // Primero la hora, para que los suscriptores de $redirects ya la vean actualizada.
  $lastUpdated.set(new Date());
  $redirects.set(redirects);
  $portUsage.set(usage);
  $loaded.set(true);
}

export async function addRedirect(target: string, alias: string): Promise<Redirect> {
  const created = await createRedirect(target, alias);
  $redirects.set([...$redirects.get().filter((r) => r.id !== created.id), created]);
  await refreshUsage();
  return created;
}

export async function renameRedirect(id: number, alias: string): Promise<Redirect> {
  const updated = await updateRedirectAlias(id, alias);
  $redirects.set($redirects.get().map((r) => (r.id === id ? updated : r)));
  return updated;
}

export async function removeRedirect(id: number): Promise<void> {
  try {
    await deleteRedirect(id);
  } catch (err) {
    // Si ya no existía, la quitamos igualmente de la vista.
    if (!(err instanceof ApiError && err.status === 404)) throw err;
  }
  $redirects.set($redirects.get().filter((r) => r.id !== id));
  await refreshUsage();
}

/**
 * Refresco periódico de estados, clientes y tráfico. Se pausa con la pestaña
 * oculta y refresca al instante al volver a ella. Nunca solapa peticiones.
 */
export function startPolling(): void {
  if (polling) return;
  polling = true;

  let timer: ReturnType<typeof setTimeout> | undefined;
  let inFlight = false;

  const tick = async (): Promise<void> => {
    clearTimeout(timer);
    if (document.visibilityState !== 'visible') return; // se reanuda en visibilitychange
    if (!inFlight) {
      inFlight = true;
      try {
        await refresh();
      } catch {
        /* error de red puntual: se reintenta en el siguiente ciclo */
      } finally {
        inFlight = false;
      }
    }
    timer = setTimeout(tick, POLL_MS);
  };

  document.addEventListener('visibilitychange', () => void tick());
  window.addEventListener('focus', () => void tick());
  timer = setTimeout(tick, POLL_MS);
}
