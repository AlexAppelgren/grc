import { presentChangePending } from '@/features/library/obligation-presentation';
import type { PresentedPill } from '@/features/shared/presentation-types';
import type { Translate } from '@/shared/i18n';
import { formatDate, formatPartialDate, type FormatContext } from '@/shared/utils/format';

import type { AnswerCitation, AnswerStatement } from './types';

// What an Ask answer reads as (design/screens/tenant-ask.html). The server
// sends facts and keys; every phrase is made here, from the catalogs.

/** The "Change pending" pill on a statement whose cited obligation a registered change will move. */
export function presentStatement(statement: AnswerStatement, t: Translate, ctx: FormatContext): PresentedPill[] {
  const date = statement.pendingChangeInForceOn;
  const precision = statement.pendingChangeInForceOnPrecision;
  if (date === null || date === undefined || precision === null || precision === undefined) return [];
  return [presentChangePending(formatPartialDate(date, precision, ctx), t)];
}

/** "FFFS 2017:2, 9 kap. 6 §, version 2": the source a numbered citation points at. */
export function citationLabel(citation: AnswerCitation, t: Translate): string {
  return t('search.ask.citation', { instrument: citation.instrumentShortName, ref: citation.refLabel, version: citation.versionNo });
}

/** The label AI output carries until a person confirms it: its basis and the date it was read at. */
export function aiBasisLabel(asOf: string, t: Translate, ctx: FormatContext): string {
  return t('search.ask.aiLabel', { date: formatDate(asOf, ctx) });
}

/** The model stopped at its length limit (`ASK_MAX_TOKENS`, D-82), so the answer may lack its last point. */
export function isCutShort(stopReason: string | null): boolean {
  return stopReason === 'max_tokens';
}
