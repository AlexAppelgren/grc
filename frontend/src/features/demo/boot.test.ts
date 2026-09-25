import { afterEach, describe, expect, it, vi } from 'vitest';

const framed = vi.hoisted(() => ({ value: false }));
vi.mock('./frame', async (importOriginal) => ({ ...(await importOriginal<object>()), isDemoFrame: () => framed.value }));

const RealDate = Date;

afterEach(() => {
  globalThis.Date = RealDate;
  vi.resetModules();
});

async function boot() {
  const { api } = await import('@/shared/utils/api-client');
  const { installDemoModeWhenFramed } = await import('./boot');
  const adapter = api.defaults.adapter;
  installDemoModeWhenFramed();
  return { api, before: adapter };
}

describe('installDemoModeWhenFramed', () => {
  it('leaves the app alone outside the demo frame', async () => {
    framed.value = false;
    const { api, before } = await boot();
    expect(api.defaults.adapter).toBe(before);
    expect(Date).toBe(RealDate);
  });

  it('answers every request from the recordings inside it, whatever adapter the caller asked for', async () => {
    framed.value = true;
    const { api } = await boot();
    const me = await api.get<{ user: unknown; permissions: string[] }>('/api/v1/me', { adapter: 'fetch' });
    expect(me.data.permissions).toContain('library.read');
    expect(Date).not.toBe(RealDate);
  });
});
