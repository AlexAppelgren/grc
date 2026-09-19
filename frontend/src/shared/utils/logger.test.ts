import { afterEach, describe, expect, it, vi } from 'vitest';

describe('logger', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it('emits every level outside production', async () => {
    vi.stubEnv('NODE_ENV', 'test');
    const debug = vi.spyOn(console, 'debug').mockImplementation(() => undefined);
    const info = vi.spyOn(console, 'info').mockImplementation(() => undefined);
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const { logger } = await import('./logger');
    logger.debug('d');
    logger.info('i', { count: 1 });
    logger.warn('w');
    logger.error('e', { requestId: 'r1' });
    expect(debug).toHaveBeenCalledWith('[cw] d');
    expect(info).toHaveBeenCalledWith('[cw] i', { count: 1 });
    expect(warn).toHaveBeenCalledWith('[cw] w');
    expect(error).toHaveBeenCalledWith('[cw] e', { requestId: 'r1' });
  });

  it('is silent except for errors in production', async () => {
    vi.stubEnv('NODE_ENV', 'production');
    const debug = vi.spyOn(console, 'debug').mockImplementation(() => undefined);
    const info = vi.spyOn(console, 'info').mockImplementation(() => undefined);
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const { logger } = await import('./logger');
    logger.debug('d');
    logger.info('i');
    logger.warn('w');
    logger.error('e');
    expect(debug).not.toHaveBeenCalled();
    expect(info).not.toHaveBeenCalled();
    expect(warn).not.toHaveBeenCalled();
    expect(error).toHaveBeenCalledWith('[cw] e');
  });
});
