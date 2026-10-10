/**
 * Guard: el panel no se muestra hasta confirmar la sesión con /api/auth/me.
 * Sin sesión válida, client.ts redirige a /login.
 * La seguridad real está en el backend; esto solo evita mostrar un panel vacío.
 */
import { me } from './api/auth';
import type { User } from '../types/redirect';

let session: Promise<User> | undefined;

/** Comprueba la sesión una sola vez; todas las llamadas comparten el resultado. */
export function requireSession(): Promise<User> {
  session ??= me();
  return session;
}

/** En /login: si ya hay sesión, ir directamente al panel. */
export async function redirectIfLoggedIn(): Promise<void> {
  try {
    await me({ redirectOn401: false });
    location.replace('/');
  } catch {
    /* sin sesión: quedarse en el login */
  }
}
