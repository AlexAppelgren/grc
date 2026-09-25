// H26: the one guard for a link to the outside world. A source address comes
// from a publisher, an agent or a bank, so it is untrusted: it renders as a
// link only when it parses as an absolute http or https URL, and otherwise
// the caller renders it as plain text.

const LINKABLE = new Set(['http:', 'https:']);

/** The address to put in `href`, or null when it must render as plain text. */
export function externalHref(url: string): string | null {
  if (!URL.canParse(url)) return null;
  return LINKABLE.has(new URL(url).protocol) ? url : null;
}
