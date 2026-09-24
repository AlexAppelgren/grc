// The public page's demo (design/public/README.md "The demo"): the real app,
// answered from recordings of the real backend. This file is the format the
// recorder journey writes and the replay reads, and the comparison CI runs to
// prove the recordings still answer everything the screens ask for.

/** One request the demo person's browser made, and what the backend answered. */
export interface DemoRecording {
  /** `GET /api/v1/watch/changes?page=1`: the method, the path and the sorted query. */
  key: string;
  status: number;
  contentType: string;
  /** Parsed JSON, or the raw text of a streamed answer (Ask). */
  body: unknown;
}

export interface DemoRecordings {
  /** When the recording was made: the demo's clock reads this as now. */
  recordedAt: string;
  entries: DemoRecording[];
}

// A map keyed by record ids or dates has one shape, whichever records it holds.
const UUID = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi;
const DATE = /\b\d{4}-(?:\d{2}-\d{2}|W\d{2})\b/g;

function canonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonical);
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, canonical((value as Record<string, unknown>)[key])]),
    );
  }
  return value;
}

/** A request body as one line with sorted keys, so the recorder and the replay spell it the same way. Only text is a body here: axios has serialised JSON by the time the replay sees it, and a file upload is a write the demo refuses anyway. */
function bodyOf(body: unknown): string {
  if (typeof body !== 'string' || body === '') return '';
  try {
    return JSON.stringify(canonical(JSON.parse(body)));
  } catch {
    return body;
  }
}

/** The key a request is recorded under: method, path, sorted query and, for a write, its body. */
export function requestKey(method: string, url: string, body?: unknown): string {
  const parsed = new URL(url, 'http://demo.invalid');
  parsed.searchParams.sort();
  const query = parsed.searchParams.toString();
  const data = bodyOf(body);
  return `${method.toUpperCase()} ${parsed.pathname}${query === '' ? '' : `?${query}`}${data === '' ? '' : ` ${data}`}`;
}

/** The same key without its query: the fallback for a filter the recorder never clicked. */
export function withoutQuery(key: string): string {
  const [method = '', target = ''] = key.split(' ');
  return `${method} ${target.replace(/\?.*$/, '')}`;
}

function templateOf(path: string, templates: readonly string[]): string | undefined {
  let best: string | undefined;
  let bestParams = Number.POSITIVE_INFINITY;
  for (const template of templates) {
    const params = template.split('{').length - 1;
    if (params >= bestParams) continue;
    const pattern = new RegExp(`^${template.replace(/\{[^}]+\}/g, '[^/]+')}$`);
    if (pattern.test(path)) {
      best = template;
      bestParams = params;
    }
  }
  return best;
}

/**
 * What a request is, without which record it asked for: the method, the path
 * template from the published API (openapi.json), the names of its query
 * parameters and the fields of its body. Two crawls of different data compare
 * equal on it, so the gate follows the API's shape and never the seed's rows.
 */
export function patternOf(key: string, templates: readonly string[]): string {
  const [method = '', target = '', ...rest] = key.split(' ');
  const [path = '', query = ''] = target.split('?');
  const names = [...new Set(new URLSearchParams(query).keys())].sort();
  let fields = '';
  if (rest.length > 0) {
    try {
      const body: unknown = JSON.parse(rest.join(' '));
      fields = body !== null && typeof body === 'object' ? ` {${Object.keys(body).sort().join(',')}}` : ' {}';
    } catch {
      fields = ' {}';
    }
  }
  return `${method} ${templateOf(path, templates) ?? path}${names.length === 0 ? '' : `?${names.join('&')}`}${fields}`;
}

/**
 * The shape of an answer: its field names and the kind of each value, never the
 * values. Null and an empty list say nothing about shape and match anything.
 */
export type Shape = string | { [field: string]: Shape } | { list: Shape };

function merge(a: Shape, b: Shape): Shape {
  if (a === 'null' || a === 'empty') return b;
  if (b === 'null' || b === 'empty') return a;
  if (typeof a === 'object' && typeof b === 'object' && 'list' in a && 'list' in b) return { list: merge(a.list, b.list) };
  if (typeof a === 'object' && typeof b === 'object' && !('list' in a) && !('list' in b)) {
    const out: Record<string, Shape> = { ...a };
    for (const [field, shape] of Object.entries(b)) out[field] = field in out ? merge(out[field] as Shape, shape) : shape;
    return out;
  }
  return a;
}

export function shapeOf(value: unknown): Shape {
  if (value === null || value === undefined) return 'null';
  if (Array.isArray(value)) return value.length === 0 ? 'empty' : { list: value.map(shapeOf).reduce(merge) };
  if (typeof value === 'object') {
    const out: Record<string, Shape> = {};
    for (const [field, inner] of Object.entries(value)) {
      const name = field.replace(UUID, ':id').replace(DATE, ':date');
      out[name] = merge(out[name] ?? 'null', shapeOf(inner));
    }
    return out;
  }
  return typeof value;
}

/** The first place two shapes differ, as a path, or null when they agree. */
export function shapeDifference(recorded: Shape, fresh: Shape, path = '$'): string | null {
  if (recorded === 'null' || recorded === 'empty' || fresh === 'null' || fresh === 'empty') return null;
  if (typeof recorded === 'string' || typeof fresh === 'string') return recorded === fresh ? null : `${path}: ${describe(recorded)} became ${describe(fresh)}`;
  if ('list' in recorded || 'list' in fresh) {
    if (!('list' in recorded) || !('list' in fresh)) return `${path}: ${describe(recorded)} became ${describe(fresh)}`;
    return shapeDifference(recorded.list, fresh.list, `${path}[]`);
  }
  for (const field of new Set([...Object.keys(recorded), ...Object.keys(fresh)])) {
    if (!(field in fresh)) return `${path}.${field}: no longer answered`;
    if (!(field in recorded)) return `${path}.${field}: new, and not in the recording`;
    const inner = shapeDifference(recorded[field] as Shape, fresh[field] as Shape, `${path}.${field}`);
    if (inner !== null) return inner;
  }
  return null;
}

function describe(shape: Shape): string {
  if (typeof shape === 'string') return shape;
  return 'list' in shape ? 'a list' : 'an object';
}

/**
 * What stops the committed recordings from answering a fresh crawl: a request
 * with no recording of its pattern and status, or an answer whose shape has
 * changed. An answer is held against its own recording when the crawl asked for
 * the very same thing (the same list of a vocabulary), and otherwise against
 * every recorded answer of its pattern taken together.
 */
export function staleness(recorded: DemoRecordings, fresh: DemoRecordings, templates: readonly string[]): string[] {
  const byKey = new Map<string, Shape>();
  const byPattern = new Map<string, Shape>();
  for (const entry of recorded.entries) {
    byKey.set(`${entry.key} ${entry.status}`, shapeOf(entry.body));
    const pattern = `${patternOf(entry.key, templates)} (${entry.status})`;
    byPattern.set(pattern, merge(byPattern.get(pattern) ?? 'null', shapeOf(entry.body)));
  }
  const problems: string[] = [];
  for (const entry of fresh.entries) {
    const pattern = `${patternOf(entry.key, templates)} (${entry.status})`;
    const shape = byKey.get(`${entry.key} ${entry.status}`) ?? byPattern.get(pattern);
    if (shape === undefined) {
      problems.push(`${pattern}: not recorded`);
      continue;
    }
    const difference = shapeDifference(shape, shapeOf(entry.body));
    if (difference !== null) problems.push(`${pattern}: ${difference}`);
  }
  return [...new Set(problems)];
}
