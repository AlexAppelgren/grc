import { describe, expect, it } from 'vitest';

import { hostSettingsFrom, routeByHost, variesByRequest, type HostRequest, type HostSettings } from './hosts';

const SPLIT: HostSettings = { publicHosts: ['bleqq.com', 'www.bleqq.com'], appHost: 'app.bleqq.com' };

function request(host: string, path: string, extra: Partial<HostRequest> = {}): HostRequest {
  return { host, path, search: '', protocol: 'https', dest: 'document', signedIn: false, ...extra };
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

  // The API's paths never reach these rules: next.config.ts passes /api on to the API on every host.
  it('sends an unknown path to the app host, which answers it as today', () => {
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
  it('keeps every app path, marked noindex, whatever the browser says about a session', () => {
    for (const path of ['/sign-in', '/enrol', '/inventory', '/console', '/not-a-page']) {
      for (const signedIn of [false, true]) expect(routeByHost(SPLIT, request('app.bleqq.com', path, { signedIn }))).toEqual({ kind: 'pass', noindex: true });
    }
  });

  it('answers a page load of / with the public page when the browser holds no session marker, a crawler included', () => {
    const publicPage = { kind: 'rewrite', path: '/welcome', canonical: 'https://bleqq.com/' };
    expect(routeByHost(SPLIT, request('app.bleqq.com', '/'))).toEqual(publicPage);
    expect(routeByHost(SPLIT, request('app.bleqq.com', '/', { dest: null }))).toEqual(publicPage);
    expect(routeByHost(SPLIT, request('APP.bleqq.com', '/', { search: '?ref=a' }))).toEqual(publicPage);
    expect(routeByHost(SPLIT, request('app.bleqq.com', '/', { protocol: 'http' }))).toEqual({ ...publicPage, canonical: 'http://bleqq.com/' });
  });

  it('keeps the app at / for a browser that says it holds a session', () => {
    expect(routeByHost(SPLIT, request('app.bleqq.com', '/', { signedIn: true }))).toEqual({ kind: 'pass', noindex: true });
    expect(routeByHost(SPLIT, request('app.bleqq.com', '/', { signedIn: true, dest: null }))).toEqual({ kind: 'pass', noindex: true });
  });

  it('keeps the app at / for the demo frame and for fetches made by the app, which are not page loads', () => {
    expect(routeByHost(SPLIT, request('app.bleqq.com', '/', { dest: 'iframe' }))).toEqual({ kind: 'pass', noindex: true });
    expect(routeByHost(SPLIT, request('app.bleqq.com', '/', { dest: 'empty' }))).toEqual({ kind: 'pass', noindex: true });
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

describe('variesByRequest', () => {
  it('holds for every page on a public host, where a page load and the demo frame get different answers at one address', () => {
    for (const host of ['bleqq.com', 'www.bleqq.com', 'BLEQQ.com']) {
      for (const path of ['/', '/welcome', '/sign-in', '/inventory']) expect(variesByRequest(SPLIT, request(host, path))).toBe(true);
    }
  });

  it('holds for the front door of the app host, where a visitor and a signed-in person get different answers', () => {
    expect(variesByRequest(SPLIT, request('app.bleqq.com', '/'))).toBe(true);
    expect(variesByRequest(SPLIT, request('APP.bleqq.com', '/'))).toBe(true);
  });

  it('holds for nothing else: the public files, the rest of the app host, another host, or the split unset', () => {
    expect(variesByRequest(SPLIT, request('bleqq.com', '/robots.txt'))).toBe(false);
    expect(variesByRequest(SPLIT, request('bleqq.com', '/demo/today-desktop-light.jpg'))).toBe(false);
    for (const path of ['/sign-in', '/inventory', '/welcome', '/robots.txt']) expect(variesByRequest(SPLIT, request('app.bleqq.com', path))).toBe(false);
    expect(variesByRequest(SPLIT, request('grc-front-staging.up.railway.app', '/'))).toBe(false);
    expect(variesByRequest(null, request('bleqq.com', '/'))).toBe(false);
    expect(variesByRequest(null, request('app.bleqq.com', '/'))).toBe(false);
  });
});
