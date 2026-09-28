import { describe, expect, it } from 'vitest';

import { hostSettingsFrom, routeByHost, type HostRequest, type HostSettings } from './hosts';

const SPLIT: HostSettings = { publicHosts: ['bleqq.com', 'www.bleqq.com'], appHost: 'app.bleqq.com' };

function request(host: string, path: string, extra: Partial<HostRequest> = {}): HostRequest {
  return { host, path, search: '', protocol: 'https', dest: 'document', ...extra };
}

describe('hostSettingsFrom', () => {
  it('reads a list of public hosts and one app host, trimmed and lower-cased', () => {
    expect(hostSettingsFrom({ PUBLIC_SITE_HOST: 'bleqq.com, WWW.bleqq.com', APP_HOST: ' app.bleqq.com ' })).toEqual(SPLIT);
  });

  it('is off unless both variables name a host', () => {
    expect(hostSettingsFrom({})).toBeNull();
    expect(hostSettingsFrom({ PUBLIC_SITE_HOST: 'bleqq.com' })).toBeNull();
    expect(hostSettingsFrom({ APP_HOST: 'app.bleqq.com' })).toBeNull();
    expect(hostSettingsFrom({ PUBLIC_SITE_HOST: ' , ', APP_HOST: 'app.bleqq.com' })).toBeNull();
    expect(hostSettingsFrom({ PUBLIC_SITE_HOST: 'bleqq.com', APP_HOST: '  ' })).toBeNull();
  });
});

describe('routeByHost with the settings unset', () => {
  it('changes nothing on any host or path', () => {
    for (const path of ['/', '/welcome', '/sign-in', '/inventory', '/console']) {
      expect(routeByHost(null, request('bleqq.com', path))).toEqual({ kind: 'pass', noindex: false });
    }
  });
});

describe('routeByHost on a public host', () => {
  it('serves the public page at /', () => {
    expect(routeByHost(SPLIT, request('bleqq.com', '/'))).toEqual({ kind: 'rewrite', path: '/welcome' });
    expect(routeByHost(SPLIT, request('www.bleqq.com', '/'))).toEqual({ kind: 'rewrite', path: '/welcome' });
  });

  it('treats a request without Sec-Fetch-Dest, a crawler, as a page load', () => {
    expect(routeByHost(SPLIT, request('bleqq.com', '/', { dest: null }))).toEqual({ kind: 'rewrite', path: '/welcome' });
    expect(routeByHost(SPLIT, request('bleqq.com', '/sign-in', { dest: null }))).toEqual({ kind: 'redirect', url: 'https://app.bleqq.com/sign-in' });
  });

  it('moves /welcome to / on the same host, keeping the query', () => {
    expect(routeByHost(SPLIT, request('bleqq.com', '/welcome', { search: '?ref=a' }))).toEqual({ kind: 'redirect', url: 'https://bleqq.com/?ref=a' });
    expect(routeByHost(SPLIT, request('www.bleqq.com', '/welcome'))).toEqual({ kind: 'redirect', url: 'https://www.bleqq.com/' });
  });

  it('sends every app, auth and console path to the same path on the app host', () => {
    for (const path of ['/sign-in', '/enrol', '/invite', '/inventory/obligations/x', '/admin/audit-log', '/console/queue', '/me/passkeys', '/dev/pills']) {
      expect(routeByHost(SPLIT, request('bleqq.com', path, { search: '?q=1' }))).toEqual({ kind: 'redirect', url: `https://app.bleqq.com${path}?q=1` });
    }
  });

  it('sends an API-client path and an unknown path to the app host, which answers them as today', () => {
    expect(routeByHost(SPLIT, request('bleqq.com', '/api/v1/auth/session'))).toEqual({ kind: 'redirect', url: 'https://app.bleqq.com/api/v1/auth/session' });
    expect(routeByHost(SPLIT, request('bleqq.com', '/not-a-page'))).toEqual({ kind: 'redirect', url: 'https://app.bleqq.com/not-a-page' });
  });

  it('keeps the public files on the public host', () => {
    for (const path of ['/robots.txt', '/sitemap.xml', '/icon.svg', '/.well-known/security.txt', '/demo/today-phone-dark.jpg']) {
      expect(routeByHost(SPLIT, request('bleqq.com', path))).toEqual({ kind: 'pass', noindex: false });
    }
  });

  it('lets the demo frame and the app inside it load on the public host', () => {
    // The frame's own load, and the app's navigations inside it (fetches), are not page loads.
    expect(routeByHost(SPLIT, request('bleqq.com', '/', { dest: 'iframe' }))).toEqual({ kind: 'pass', noindex: true });
    expect(routeByHost(SPLIT, request('bleqq.com', '/inventory', { dest: 'empty' }))).toEqual({ kind: 'pass', noindex: true });
    expect(routeByHost(SPLIT, request('bleqq.com', '/welcome', { dest: 'iframe' }))).toEqual({ kind: 'pass', noindex: true });
  });

  it('uses the scheme the request came in on', () => {
    expect(routeByHost(SPLIT, request('bleqq.com', '/sign-in', { protocol: 'http' }))).toEqual({ kind: 'redirect', url: 'http://app.bleqq.com/sign-in' });
  });

  it('matches the host whatever its case', () => {
    expect(routeByHost(SPLIT, request('BLEQQ.com', '/'))).toEqual({ kind: 'rewrite', path: '/welcome' });
  });
});

describe('routeByHost on the app host', () => {
  it('keeps / and every app path, marked noindex', () => {
    for (const path of ['/', '/sign-in', '/enrol', '/inventory', '/console', '/not-a-page']) {
      expect(routeByHost(SPLIT, request('app.bleqq.com', path))).toEqual({ kind: 'pass', noindex: true });
    }
  });

  it('sends the public page to the first public host, from a page load and from the app alike', () => {
    expect(routeByHost(SPLIT, request('app.bleqq.com', '/welcome'))).toEqual({ kind: 'redirect', url: 'https://bleqq.com/' });
    expect(routeByHost(SPLIT, request('app.bleqq.com', '/welcome', { dest: 'empty', search: '?x=1' }))).toEqual({ kind: 'redirect', url: 'https://bleqq.com/?x=1' });
  });

  it('leaves its files alone', () => {
    expect(routeByHost(SPLIT, request('app.bleqq.com', '/robots.txt'))).toEqual({ kind: 'pass', noindex: false });
  });
});

describe('routeByHost on any other host', () => {
  it('behaves as today, so the platform health check and its own address keep working', () => {
    for (const path of ['/', '/welcome', '/sign-in']) {
      expect(routeByHost(SPLIT, request('frontend-production.up.railway.app', path))).toEqual({ kind: 'pass', noindex: false });
      expect(routeByHost(SPLIT, request('', path))).toEqual({ kind: 'pass', noindex: false });
    }
  });
});
