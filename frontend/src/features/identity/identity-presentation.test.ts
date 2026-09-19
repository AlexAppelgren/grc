import { describe, expect, it } from 'vitest';

import { createT } from '@/shared/i18n';

import { describeDevice, presentPasskey, presentSession } from './identity-presentation';

const t = createT('en');

describe('presentPasskey', () => {
  it('labels the device type from the kind, both neutral', () => {
    expect(presentPasskey({ deviceType: 'multi_device' }, t)).toEqual([{ key: 'device:multi_device', label: 'Synced', tone: 'information', order: 10 }]);
    expect(presentPasskey({ deviceType: 'single_device' }, t)).toEqual([{ key: 'device:single_device', label: 'Device-bound', tone: 'information', order: 10 }]);
  });

  it('shows nothing for a kind it does not know', () => {
    expect(presentPasskey({ deviceType: 'later' as 'multi_device' }, t)).toEqual([]);
  });
});

describe('presentSession', () => {
  it('marks the current session as this device, positive', () => {
    expect(presentSession({ current: true }, t)).toEqual([{ key: 'session:current', label: 'This device', tone: 'positive', order: 10 }]);
    expect(presentSession({ current: false }, t)).toEqual([]);
  });
});

describe('describeDevice', () => {
  it('names browser and system from common user agents', () => {
    expect(describeDevice('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36', t)).toBe('Chrome on Windows');
    expect(describeDevice('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0', t)).toBe('Edge on Windows');
    expect(describeDevice('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1', t)).toBe('Safari on iPhone');
    expect(describeDevice('Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) Gecko/20100101 Firefox/130.0', t)).toBe('Firefox on macOS');
    expect(describeDevice('Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/129.0 Mobile Safari/537.36', t)).toBe('Chrome on Android');
  });

  it('falls back to what it knows, the raw string, or the unknown text', () => {
    expect(describeDevice('Mozilla/5.0 (X11; CrOS x86_64) Gecko', t)).toBe('ChromeOS');
    expect(describeDevice('curl/8.0', t)).toBe('curl/8.0');
    expect(describeDevice(`${'x'.repeat(70)}`, t)).toBe(`${'x'.repeat(57)}…`);
    expect(describeDevice('', t)).toBe('Unknown device');
    expect(describeDevice(null, t)).toBe('Unknown device');
  });
});
