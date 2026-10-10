import type { PortUsage, Redirect } from '../../types/redirect';
import { request } from './client';

export function listRedirects(): Promise<Redirect[]> {
  return request<Redirect[]>('/redirects');
}

export function createRedirect(target: string, alias: string): Promise<Redirect> {
  return request<Redirect>('/redirects', { method: 'POST', body: { target, alias } });
}

export function updateRedirectAlias(id: number, alias: string): Promise<Redirect> {
  return request<Redirect>(`/redirects/${id}`, { method: 'PATCH', body: { alias } });
}

export function deleteRedirect(id: number): Promise<void> {
  return request<void>(`/redirects/${id}`, { method: 'DELETE' });
}

export function getPortUsage(): Promise<PortUsage> {
  return request<PortUsage>('/ports/usage');
}
