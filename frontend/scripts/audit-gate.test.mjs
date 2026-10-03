import { describe, expect, it } from 'vitest';

import { acceptedAdvisories, blockingAdvisories } from './audit-gate.mjs';

const TOML = `# Advisories accepted
[[IgnoredVulns]]
id = "GHSA-vfj7-8cjw-p6xm"
ignoreUntil = 2026-11-02
reason = "build-only"

[[IgnoredVulns]]
id = "GHSA-aaaa-bbbb-cccc"
reason = "no expiry"
`;

// The shape of `npm audit --json`: the advisory sits in one package's `via`,
// and every package that depends on it names that package instead.
function audit(url, severity = 'high') {
  return {
    vulnerabilities: {
      braces: { severity, via: [{ source: 1, name: 'braces', title: 'stack exhaustion', url, severity }] },
      micromatch: { severity, via: ['braces'] },
    },
  };
}

describe('acceptedAdvisories', () => {
  it('reads each id with its expiry, or none', () => {
    expect(acceptedAdvisories(TOML)).toEqual([
      { id: 'GHSA-vfj7-8cjw-p6xm', until: '2026-11-02' },
      { id: 'GHSA-aaaa-bbbb-cccc', until: null },
    ]);
  });

  it('accepts nothing from a file without entries', () => {
    expect(acceptedAdvisories('# nothing accepted\n')).toEqual([]);
  });
});

describe('blockingAdvisories', () => {
  const accepted = acceptedAdvisories(TOML);

  it('lets an accepted advisory pass until its expiry, and the packages that depend on it with it', () => {
    expect(blockingAdvisories(audit('https://github.com/advisories/GHSA-vfj7-8cjw-p6xm'), accepted, '2026-11-01')).toEqual([]);
  });

  it('fails an accepted advisory from its expiry on', () => {
    expect(blockingAdvisories(audit('https://github.com/advisories/GHSA-vfj7-8cjw-p6xm'), accepted, '2026-11-02')).toEqual([
      'GHSA-vfj7-8cjw-p6xm (high) in braces: stack exhaustion',
    ]);
  });

  it('fails any advisory nobody accepted, at moderate or worse, and lets a low one pass as npm audit does', () => {
    expect(blockingAdvisories(audit('https://github.com/advisories/GHSA-zzzz-yyyy-xxxx', 'moderate'), accepted, '2026-10-03')).toHaveLength(1);
    expect(blockingAdvisories(audit('https://github.com/advisories/GHSA-zzzz-yyyy-xxxx', 'low'), accepted, '2026-10-03')).toEqual([]);
  });

  it('keeps an entry without an expiry accepted', () => {
    expect(blockingAdvisories(audit('https://github.com/advisories/GHSA-aaaa-bbbb-cccc'), accepted, '2030-01-01')).toEqual([]);
  });

  it('passes a clean answer', () => {
    expect(blockingAdvisories({ vulnerabilities: {} }, accepted, '2026-10-03')).toEqual([]);
  });
});
