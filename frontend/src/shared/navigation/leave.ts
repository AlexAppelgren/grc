import { PUBLIC_HOME } from './registry';

/**
 * Leaves for the public page with a page load, never a client-side route
 * change. On the app's own host the server answers the public page's address
 * by moving to the public host (src/proxy.ts), which is another origin: the
 * router's fetch of it was refused by the browser on every such move, and on
 * every load of the sign-in page, whose back link the router fetched ahead of
 * the click, before the router fell back to a page load. A page load is
 * answered by the server on every host, and after a sign-out it also drops
 * whatever the page still held in memory.
 */
export function leaveForPublicPage(): void {
  window.location.replace(PUBLIC_HOME);
}
