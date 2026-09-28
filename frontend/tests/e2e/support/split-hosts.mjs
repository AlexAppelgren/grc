// The E2E stack's second web server: the same production build, with the public
// site and the app on hosts of their own (src/proxy.ts). The browser reaches the
// app host as localhost:<E2E_SPLIT_PORT>, so it shares a site with the API on
// localhost and the passkeys' RP ID, and the public host as
// public.localhost:<E2E_SPLIT_PORT>, which Chromium resolves to this machine.
//
// Next hands its proxy a URL built from localhost and the port it listens on, and
// writes a redirect to that same origin as a relative one. Deployed, the
// platform's edge sits in front, so the app host is never Next's own origin and a
// redirect to it stays absolute. This file plays that edge: it takes the port the
// browser uses and passes every connection, Host header and all, to Next on the
// next port up.
import { spawn } from 'node:child_process';
import net from 'node:net';

const port = Number(process.env.E2E_SPLIT_PORT);
const nextPort = port + 1;

const next = spawn('npm', ['run', 'start', '--', '--port', String(nextPort)], { stdio: 'inherit' });
next.on('exit', (code) => process.exit(code ?? 1));
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => next.kill(signal));

net
  .createServer((browser) => {
    const upstream = net.connect(nextPort, '127.0.0.1');
    browser.pipe(upstream).pipe(browser);
    browser.on('error', () => upstream.destroy());
    upstream.on('error', () => browser.destroy());
  })
  .listen(port);
