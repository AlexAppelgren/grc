// What the web server answers itself before it passes an API call on (src/proxy.ts,
// next.config.ts; D-134, ADR 0068). Next cuts a request body above its limit and passes
// the rest on. The API then waits for bytes that never come and keeps one of its workers
// busy until the wait ends (measured 2026-11-12), and a handful of such calls would
// occupy them all. So a body above the limit, or one that does not say how large it is,
// is refused here and never reaches the API.

/** The largest request body passed on to the API: just above the API's own cap for a file
 * (EVIDENCE_MAX_BYTES, 25 MiB), with room for the form around it. Next holds each body in
 * memory while it passes it on, so the limit is no larger than it has to be. */
export const API_MAX_BODY_BYTES = Number(process.env.API_INTERNAL_MAX_BODY_BYTES) || 26 * 1024 * 1024;

/** A refusal in the API's own problem format: the client branches on `code`. */
export interface BodyRefusal {
  title: string;
  status: 411 | 413;
  detail: string;
  code: 'length_required' | 'payload_too_large';
}

const LENGTH_REQUIRED: BodyRefusal = { title: 'Length Required', status: 411, detail: 'The request does not say how large it is.', code: 'length_required' };
const TOO_LARGE: BodyRefusal = { title: 'Content Too Large', status: 413, detail: 'This is too large to send. Choose a smaller file.', code: 'payload_too_large' };

/** `contentLength` and `transferEncoding` are the request's headers, null when absent. */
export function bodyRefusal(contentLength: string | null, transferEncoding: string | null, maxBytes: number): BodyRefusal | null {
  if (transferEncoding !== null) return LENGTH_REQUIRED;
  return contentLength !== null && Number(contentLength) > maxBytes ? TOO_LARGE : null;
}
