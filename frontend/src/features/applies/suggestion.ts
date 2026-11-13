import { localeTags, type Translate } from '@/shared/i18n';
import { formatDate, type FormatContext } from '@/shared/utils/format';

import type { ApplicabilityRegulation } from './api';

// The reason the Decide dialog suggests (Alex, 2026-11-12: help with the reason field).
// Built here from facts the bank already holds, with no model call: what brings each
// regulation into the company's scope (`through`: its regime and the register lines that
// give it) and, when the company has register facts, where and when they were read. It
// states those facts and never the conclusion; the person edits it, and with "Does not
// apply" the dialog suggests nothing, because the fact that takes a company outside a
// rule is theirs to give.

/** What brings one regulation into a company's scope: its regime's label and the register lines that give it. */
export interface Basis {
  term: string;
  lines: readonly string[];
}

/** Where and when the company's register facts were read. */
export interface RegisterRead {
  authority: string;
  readAt: string;
}

export function basisOf(regulation: Pick<ApplicabilityRegulation, 'through'>): Basis {
  return { term: regulation.through.term.label, lines: regulation.through.lines };
}

const sameBasis = (a: Basis, b: Basis): boolean => a.term === b.term && a.lines.join('\n') === b.lines.join('\n');

/**
 * One basis common to every regulation the decision covers is said as it is: through the
 * company's licence lines, or through the bank's scope where no line gives the regime.
 * Several bases are said together. The register sentence follows when there are facts
 * and the reason names the company's licences.
 */
export function suggestReason(bases: readonly Basis[], company: string, register: RegisterRead | null, t: Translate, ctx: FormatContext): string {
  const distinct = bases.filter((basis, index) => bases.findIndex((other) => sameBasis(other, basis)) === index);
  const only = distinct.length === 1 ? distinct[0] : undefined;
  const scope =
    only === undefined
      ? t('applies.suggest.several', { company })
      : only.lines.length > 0
        ? t('applies.suggest.licence', { count: only.lines.length, lines: new Intl.ListFormat(localeTags[ctx.locale], { type: 'conjunction' }).format(only.lines), term: only.term })
        : t('applies.suggest.scope', { term: only.term, company });
  // The register gives the licence lines, never the bank's scope: a reason resting on the
  // scope alone gets no register sentence.
  const fromScope = only !== undefined && only.lines.length === 0;
  return register === null || fromScope ? scope : `${scope} ${t('applies.suggest.register', { authority: register.authority, date: formatDate(register.readAt, ctx) })}`;
}
