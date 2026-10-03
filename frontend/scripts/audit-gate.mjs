// The npm audit gate (CLAUDE.md §7): what `npm audit --audit-level=moderate`
// fails on, less the advisories Alex accepted in osv-scanner.toml beside the
// lockfile, each only until its ignoreUntil (D-119). npm audit cannot set one
// advisory aside, and the two scanners must accept the same list, so this reads
// npm audit's JSON instead. Every finding there traces back to an advisory
// object in some package's `via`; the run fails on any advisory of moderate
// severity or worse that is not accepted, or whose acceptance has run out.
// Exits 1 on any finding, and on an answer it cannot read.
import { spawnSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const BLOCKING = new Set(['moderate', 'high', 'critical']);

/** The accepted advisories of an osv-scanner.toml: [{ id, until }], `until` a YYYY-MM-DD or null. */
export function acceptedAdvisories(toml) {
  return toml
    .split(/^\[\[IgnoredVulns\]\]\s*$/m)
    .slice(1)
    .map((block) => ({
      id: /^id\s*=\s*"([^"]+)"/m.exec(block)?.[1],
      until: /^ignoreUntil\s*=\s*(\d{4}-\d{2}-\d{2})/m.exec(block)?.[1] ?? null,
    }))
    .filter((entry) => entry.id !== undefined);
}

/** The advisories in an `npm audit --json` answer that fail the gate on `today` (YYYY-MM-DD). */
export function blockingAdvisories(audit, accepted, today) {
  const open = new Set(accepted.filter((entry) => entry.until === null || today < entry.until).map((entry) => entry.id));
  const found = new Map();
  for (const [name, finding] of Object.entries(audit.vulnerabilities ?? {})) {
    for (const via of finding.via) {
      if (typeof via === 'string' || !BLOCKING.has(via.severity)) continue;
      const id = /GHSA(-[a-z0-9]{4}){3}$/.exec(via.url ?? '')?.[0] ?? via.url ?? String(via.source);
      if (!open.has(id)) found.set(id, `${id} (${via.severity}) in ${name}: ${via.title}`);
    }
  }
  return [...found.values()];
}

const here = dirname(fileURLToPath(import.meta.url));

if (process.argv[1] !== undefined && pathToFileURL(process.argv[1]).href === import.meta.url) {
  // npm's own entry point under this Node: Windows has no `npm` executable to spawn.
  const npm = process.env.npm_execpath;
  if (npm === undefined) {
    console.error('audit-gate: run it as `npm run audit:gate`, which tells it where npm is');
    process.exit(1);
  }
  const run = spawnSync(process.execPath, [npm, 'audit', '--json'], { cwd: join(here, '..'), encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  let audit;
  try {
    audit = JSON.parse(run.stdout);
  } catch {
    console.error(`audit-gate: npm audit gave no answer to read\n${run.stderr}`);
    process.exit(1);
  }
  if (audit.error !== undefined) {
    console.error(`audit-gate: npm audit failed: ${JSON.stringify(audit.error)}`);
    process.exit(1);
  }
  const accepted = acceptedAdvisories(readFileSync(join(here, '..', 'osv-scanner.toml'), 'utf8'));
  const today = new Date().toISOString().slice(0, 10);
  const problems = blockingAdvisories(audit, accepted, today);
  if (problems.length > 0) {
    console.error(`audit-gate: ${problems.length} advisory(ies) of moderate severity or worse\n  ${problems.join('\n  ')}`);
    process.exit(1);
  }
  const held = accepted.filter((entry) => entry.until === null || today < entry.until).map((entry) => `${entry.id} until ${entry.until ?? 'withdrawn'}`);
  console.log(`audit-gate: ok${held.length > 0 ? `; accepted: ${held.join(', ')}` : ''}`);
}
