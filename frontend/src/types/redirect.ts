export type RedirectStatus = 'pending' | 'active' | 'error' | 'stopped';

export interface Redirect {
  id: number;
  alias: string;
  target: string;
  is_domain: boolean;
  resolved_ip: string;
  resolved_port: number;
  resolved_address: string;
  port: number;
  public_address: string;
  status: RedirectStatus;
  error: string | null;
  created_at: string;
  resolved_at: string | null;
  clients: number;
  bytes_in: number;
  bytes_out: number;
}

export interface PortUsage {
  public_host: string;
  used: number;
  total: number;
  free: number;
  range_start: number;
  range_end: number;
}

export interface User {
  username: string;
}
