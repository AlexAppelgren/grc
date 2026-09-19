// ICU-lite message formatting. Supports `{name}` substitution and
// `{name, plural, =0 {…} one {…} other {…}}` with `#` for the number, using
// Intl.PluralRules for the category. Branches may nest. next-intl is not in the
// Phase 0 pins, and this is all the catalogs need (playbook 6.5, 6.7:
// computed labels come from the catalogs with plural forms).

export type MessageVars = Record<string, string | number>;

function matchingBrace(text: string, openAt: number): number {
  let depth = 0;
  for (let i = openAt; i < text.length; i += 1) {
    const ch = text[i];
    if (ch === '{') depth += 1;
    if (ch === '}') {
      depth -= 1;
      if (depth === 0) return i;
    }
  }
  return -1;
}

function parseBranches(body: string): Map<string, string> {
  const branches = new Map<string, string>();
  let i = 0;
  while (i < body.length) {
    while (i < body.length && body[i] === ' ') i += 1;
    const open = body.indexOf('{', i);
    if (open === -1) break;
    const selector = body.slice(i, open).trim();
    const close = matchingBrace(body, open);
    if (close === -1) break;
    branches.set(selector, body.slice(open + 1, close));
    i = close + 1;
  }
  return branches;
}

function selectBranch(branches: Map<string, string>, count: number, localeTag: string): string {
  const exact = branches.get(`=${count}`);
  if (exact !== undefined) return exact;
  const category = new Intl.PluralRules(localeTag).select(count);
  return branches.get(category) ?? branches.get('other') ?? '';
}

export function formatMessage(message: string, vars: MessageVars, localeTag: string): string {
  let out = '';
  let i = 0;
  while (i < message.length) {
    const open = message.indexOf('{', i);
    if (open === -1) {
      out += message.slice(i);
      break;
    }
    out += message.slice(i, open);
    const close = matchingBrace(message, open);
    if (close === -1) {
      out += message.slice(open);
      break;
    }
    const inner = message.slice(open + 1, close);
    const firstComma = inner.indexOf(',');
    if (firstComma === -1) {
      const name = inner.trim();
      const value = vars[name];
      out += value === undefined ? `{${name}}` : String(value);
    } else {
      const name = inner.slice(0, firstComma).trim();
      const rest = inner.slice(firstComma + 1).trim();
      const secondComma = rest.indexOf(',');
      const kind = (secondComma === -1 ? rest : rest.slice(0, secondComma)).trim();
      const raw = vars[name];
      if (kind === 'plural' && typeof raw === 'number') {
        const branch = selectBranch(parseBranches(rest.slice(secondComma + 1)), raw, localeTag);
        const number = new Intl.NumberFormat(localeTag).format(raw);
        out += formatMessage(branch.replaceAll('#', number), vars, localeTag);
      } else {
        out += raw === undefined ? `{${name}}` : String(raw);
      }
    }
    i = close + 1;
  }
  return out;
}
