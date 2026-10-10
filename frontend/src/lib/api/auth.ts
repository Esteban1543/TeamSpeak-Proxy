import type { User } from '../../types/redirect';
import { request } from './client';

export function login(username: string, password: string): Promise<User> {
  return request<User>('/auth/login', {
    method: 'POST',
    body: { username, password },
    redirectOn401: false,
  });
}

export function logout(): Promise<void> {
  return request<void>('/auth/logout', { method: 'POST', redirectOn401: false });
}

export function me(options: { redirectOn401?: boolean } = {}): Promise<User> {
  return request<User>('/auth/me', options);
}
