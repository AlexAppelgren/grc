import { NextResponse, type NextRequest } from 'next/server';

import { hostSettingsFrom, routeByHost, variesByDest } from '@/shared/navigation/hosts';

// The public site and the app on their own hosts (shared/navigation/hosts.ts).
// Read at run time, so the same build serves every environment; with
// PUBLIC_SITE_HOST or APP_HOST unset every request passes untouched.
export function proxy(request: NextRequest): NextResponse {
  // The scheme the platform's edge saw, and only a web one: the header can come from anyone.
  const forwardedProto = request.headers.get('x-forwarded-proto')?.split(',')[0]?.trim();
  const protocol = forwardedProto === 'https' || forwardedProto === 'http' ? forwardedProto : request.nextUrl.protocol.replace(/:$/, '');
  const settings = hostSettingsFrom(process.env);
  const hostRequest = {
    host: request.headers.get('x-forwarded-host') ?? request.headers.get('host') ?? '',
    path: request.nextUrl.pathname,
    search: request.nextUrl.search,
    protocol,
    dest: request.headers.get('sec-fetch-dest'),
  };
  const route = routeByHost(settings, hostRequest);
  const response =
    route.kind === 'redirect' ? NextResponse.redirect(route.url, 301) : route.kind === 'rewrite' ? NextResponse.rewrite(new URL(route.path, request.url)) : NextResponse.next();
  if (route.kind === 'pass' && route.noindex) response.headers.set('X-Robots-Tag', 'noindex');
  // One address, two answers: never stored by the edge, and checked again by the browser each time.
  if (variesByDest(settings, hostRequest)) response.headers.set('Cache-Control', 'private, no-cache');
  return response;
}

// Everything but the build's own files, which every host serves.
export const config = { matcher: ['/((?!_next/).*)'] };
