import { describe, expect, it } from 'vitest';

import { bankAgentName, hourLabel, nextRunOf, parseCap, refusals, scopeMarkets, spendOf, weekdayLabel, type RefusalCode } from '@/components/admin/admin-agents';
import { createT } from '@/shared/i18n';

// The pure parts of /admin/agents: how each refusal code reads, the spend
// against the one monthly cap, when an agent next runs, and the order its
// markets are offered in.

const t = createT('en');

const agent = { enabled: true, pausedAt: null, pausedBy: null, cadence: 'weekly' as const, nextRunAt: '2026-09-28T04:00:00Z' };
const org = { aiEnabled: true, capReached: false };

describe('refusals', () => {
  const said = refusals(t);
  const expected: Record<Exclude<RefusalCode, 'step_up_required'>, string> = {
    above_plan_limit: 'Our plan does not allow this, so nothing changed.',
    unknown_key: 'That choice is no longer offered. Reload the page and choose again.',
    duplicate_key: 'We have already added this agent.',
    no_tenant_agent: "Add an agent of our own first. bleqq's watch runs on its own schedule and takes no requests.",
    plan_limit_reached: "Our plan's requests for this period are used up. Try again later.",
    budget_cap_reached: "This month's cap is reached, so nothing more runs until next month or until the cap is raised.",
    budget_cap_required: 'Set the monthly cap before switching an agent on.',
    agent_paused: 'The agent is paused. Resume it first.',
    agent_disabled: 'The agent is switched off. Switch it on first.',
    feature_off: 'AI features are off for the organisation, so our agents do not run.',
    run_finished: 'The run had already finished, so there was nothing to stop.',
  };

  for (const [code, sentence] of Object.entries(expected)) {
    it(`renders ${code} as its own sentence`, () => {
      expect(said[code as RefusalCode]).toBe(sentence);
    });
  }

  it('gives every code a different sentence, so no two refusals read alike', () => {
    const sentences = Object.values(expected);
    expect(new Set(sentences).size).toBe(sentences.length);
  });

  it('reads a refused passkey as nothing changed', () => {
    expect(said.step_up_required).toBe(t('problem.stepUpCancelled'));
  });
});

describe('spendOf', () => {
  it('draws no meter without a cap, never an empty one', () => {
    expect(spendOf({ monthlyCap: null, spentThisMonth: '0.00' })).toEqual({ spent: 0, cap: null, percent: null, reached: false });
  });

  it('gives the whole percent of the cap spent', () => {
    expect(spendOf({ monthlyCap: '40.00', spentThisMonth: '7.35' })).toEqual({ spent: 7.35, cap: 40, percent: 18, reached: false });
  });

  it('is reached at the cap, and a cap below the spend reads as full', () => {
    expect(spendOf({ monthlyCap: '40.00', spentThisMonth: '40.00' })).toMatchObject({ percent: 100, reached: true });
    expect(spendOf({ monthlyCap: '0.00', spentThisMonth: '3.00' })).toMatchObject({ percent: 100, reached: true });
  });
});

describe('nextRunOf', () => {
  it('names the scheduled start when nothing holds the agent', () => {
    expect(nextRunOf(agent, org)).toEqual({ kind: 'at', at: '2026-09-28T04:00:00Z' });
  });

  it('says off, then paused by a person or by the cap, before anything else', () => {
    expect(nextRunOf({ ...agent, enabled: false, pausedAt: '2026-09-20T00:00:00Z' }, { aiEnabled: false, capReached: true })).toEqual({ kind: 'off' });
    expect(nextRunOf({ ...agent, pausedAt: '2026-09-20T00:00:00Z', pausedBy: { id: 'u1', name: 'Erik Holm' } }, org)).toEqual({ kind: 'paused' });
    expect(nextRunOf({ ...agent, pausedAt: '2026-09-20T00:00:00Z' }, org)).toEqual({ kind: 'capPaused' });
  });

  it('waits while AI features are off or the cap is reached', () => {
    expect(nextRunOf(agent, { aiEnabled: false, capReached: true })).toEqual({ kind: 'aiOff' });
    expect(nextRunOf(agent, { aiEnabled: true, capReached: true })).toEqual({ kind: 'capReached' });
  });

  it('runs a manual agent only when asked, and says so when nothing is scheduled', () => {
    expect(nextRunOf({ ...agent, cadence: 'manual', nextRunAt: null }, org)).toEqual({ kind: 'manual' });
    expect(nextRunOf({ ...agent, nextRunAt: null }, org)).toEqual({ kind: 'unscheduled' });
  });
});

describe('scopeMarkets', () => {
  it('offers the operating markets first, then the watched ones, and never one not followed', () => {
    const market = (key: string, level: 'operating' | 'watching' | 'not_followed') => ({ jurisdiction: { key, kind: 'country', label: key }, level });
    const ordered = scopeMarkets([market('no', 'watching'), market('se', 'operating'), market('dk', 'not_followed'), market('fi', 'operating')]);
    expect(ordered.map((m) => m.jurisdiction.key)).toEqual(['se', 'fi', 'no']);
  });
});

describe('the smaller readings', () => {
  it('takes a cap in euro with at most two decimals, a comma included', () => {
    expect(parseCap(' 40 ')).toBe('40');
    expect(parseCap('40,5')).toBe('40.5');
    expect(parseCap('40.00')).toBe('40.00');
    expect(parseCap('-1')).toBeNull();
    expect(parseCap('40.001')).toBeNull();
    expect(parseCap('forty')).toBeNull();
  });

  it('names a shipped definition in words and any other by its key', () => {
    expect(bankAgentName('tenant-source-watch', t)).toBe('Source checker');
    expect(bankAgentName('bank-new-thing', t)).toBe('Bank new thing');
  });

  it('reads run days in the reader language and hours on the 24-hour clock', () => {
    expect(weekdayLabel(1, 'en')).toBe('Monday');
    expect(weekdayLabel(7, 'sv')).toBe('söndag');
    expect(hourLabel(6)).toBe('06:00');
  });
});
