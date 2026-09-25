import { api } from '@/shared/utils/api-client';

import type { ConsoleTenant, ConsoleTenantCreate, ConsoleTenantPage, PageQuery } from './types';

// Thin typed wrappers returning `.data` (playbook 6.1). The console reads the
// tenant rows and writes one; nothing under a tenant is ever asked for, so
// platform staff keep no way into a bank's own data (ADM-02).

const CONSOLE_TENANTS = '/api/v1/console/tenants';

export async function listConsoleTenants(query: PageQuery): Promise<ConsoleTenantPage> {
  return (await api.get<ConsoleTenantPage>(CONSOLE_TENANTS, { params: query })).data;
}

export async function createConsoleTenant(body: ConsoleTenantCreate): Promise<ConsoleTenant> {
  return (await api.post<ConsoleTenant>(CONSOLE_TENANTS, body)).data;
}
