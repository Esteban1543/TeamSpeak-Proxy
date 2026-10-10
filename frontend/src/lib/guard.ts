/**
 * Guard: el panel no se muestra hasta confirmar la sesión con /api/auth/me.
 * Sin sesión válida, client.ts redirige a /login.
 * La seguridad real está en el backend; esto solo evita mostrar un panel vacío.
 */
import { me } from './api/auth';
import type { User } from '../types/redirect';

export async function requireSession(): Promise<User> {
  return me();
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
