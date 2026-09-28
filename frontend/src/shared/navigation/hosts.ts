import { PUBLIC_HOME } from './registry';

// Two hosts, one build (docs/runbooks/DNS_DOMAINS.md "The public site and the
// app on their own hosts"). A bank's web filter scores a young domain on what it
// sees without JavaScript, and a front door that is an empty page loading a
// sign-in is the phishing profile. So the public page gets hosts of its own
// (PUBLIC_SITE_HOST, a list: bleqq.com, www.bleqq.com) and the app one of its
// own (APP_HOST: compliance-test.bleqq.com). Both are read at run time by
// src/proxy.ts; until both are set nothing changes on any host.
//
// On a public host a page load of / is the public page, rendered on the server;
// /welcome moves to /; everything else moves to the same address on the app
// host. The public page frames the app as its demo, which has to stay on the
// page's own origin (features/demo/frame.ts), so only a page load moves: the
// frame's own load and the app's fetches inside it carry another
// Sec-Fetch-Dest and pass. A request without the header, a crawler, is a page
// load. On the app host the app works as today, sends noindex, and its link to
// the public page moves to the public host. Any other host (the platform's own
// address, its health check) behaves as today.

export interface HostSettings {
  /** The first is where the app host sends a visitor to the public page. */
  publicHosts: readonly [string, ...string[]];
  appHost: string;
}

export interface HostRequest {
  host: string;
  path: string;
  /** The query with its `?`, or empty. */
  search: string;
  protocol: string;
  /** Sec-Fetch-Dest, or null when the client sent none. */
  dest: string | null;
}

export type HostRoute = { kind: 'pass'; noindex: boolean } | { kind: 'rewrite'; path: string } | { kind: 'redirect'; url: string };

/** The files every host serves as they are: what crawlers, filters and the public page load. */
const PUBLIC_FILES = ['/robots.txt', '/sitemap.xml', '/icon.svg'];
const PUBLIC_FILE_DIRS = ['/.well-known/', '/demo/'];

function hostOf(value: string): string {
  return value.trim().toLowerCase();
}

/** The split, or null (today's single host) unless both variables name a host. */
export function hostSettingsFrom(env: Readonly<Record<string, string | undefined>>): HostSettings | null {
  const [first, ...rest] = (env.PUBLIC_SITE_HOST ?? '').split(',').map(hostOf).filter((host) => host !== '');
  const appHost = hostOf(env.APP_HOST ?? '');
  return first !== undefined && appHost !== '' ? { publicHosts: [first, ...rest], appHost } : null;
}

export function routeByHost(settings: HostSettings | null, request: HostRequest): HostRoute {
  const host = hostOf(request.host);
  const isFile = PUBLIC_FILES.includes(request.path) || PUBLIC_FILE_DIRS.some((dir) => request.path.startsWith(dir));
  if (settings === null || isFile) return { kind: 'pass', noindex: false };
  const on = (target: string, path: string) => `${request.protocol}://${target}${path}${request.search}`;

  if (host === settings.appHost) {
    return request.path === PUBLIC_HOME ? { kind: 'redirect', url: on(settings.publicHosts[0], '/') } : { kind: 'pass', noindex: true };
  }
  if (!settings.publicHosts.includes(host)) return { kind: 'pass', noindex: false };
  if (request.dest !== null && request.dest !== 'document') return { kind: 'pass', noindex: true };
  if (request.path === '/') return { kind: 'rewrite', path: PUBLIC_HOME };
  if (request.path === PUBLIC_HOME) return { kind: 'redirect', url: on(host, '/') };
  return { kind: 'redirect', url: on(settings.appHost, request.path) };
}
