import type { PillTone } from '@/components/ui/pill-tones';
import { byOrder, type PresentedPill } from '@/features/shared/presentation-types';
import { slotTone } from '@/features/shared/tone-by-kind';
import { localeTags, type MessageKey, type Translate } from '@/shared/i18n';
import type { FormatContext } from '@/shared/utils/format';

import type { EvalBaseline, EvalQuestion, EvalScores } from './api';

// How the evaluation page reads its records. Every pill's tone comes from the
// question's own facts, never from a choice: a question the gate scores is
// positive, one added here and not yet shipped to the gate needs someone to do
// that (warning), and a retired one is a plain fact.

export type GateKind = 'in_gate' | 'not_in_gate' | 'retired';

const GATE_TONE: Record<GateKind, PillTone> = {
  in_gate: 'positive',
  not_in_gate: 'warning',
  retired: 'information',
};

const GATE_KEY = {
  in_gate: 'console.evaluation.gate.inGate',
  not_in_gate: 'console.evaluation.gate.notInGate',
  retired: 'console.evaluation.gate.retired',
} as const satisfies Record<GateKind, MessageKey>;

export const MATCH_KIND_KEY = {
  keyword: 'search.matchKind.keyword',
  concept: 'search.matchKind.concept',
  both: 'search.matchKind.both',
} as const satisfies Record<EvalQuestion['matchKind'], MessageKey>;

const QUESTION_SLOT_ORDER = { gate: 10, language: 20, matchKind: 30 } as const;

export function gateKind(question: EvalQuestion): GateKind {
  if (!question.active) return 'retired';
  return question.inGate ? 'in_gate' : 'not_in_gate';
}

/** A language key's label from the language rows, or the key while they have not answered. */
export function languageLabel(key: string, languages: readonly { key: string; label: string }[] | undefined): string {
  return languages?.find((language) => language.key === key)?.label ?? key;
}

export function presentQuestion(question: EvalQuestion, t: Translate, languages: readonly { key: string; label: string }[] | undefined): PresentedPill[] {
  const gate = gateKind(question);
  const pills: PresentedPill[] = [
    { key: `gate:${gate}`, label: t(GATE_KEY[gate]), tone: GATE_TONE[gate], order: QUESTION_SLOT_ORDER.gate },
    { key: `lang:${question.lang}`, label: languageLabel(question.lang, languages), tone: 'information', order: QUESTION_SLOT_ORDER.language },
    { key: `match:${question.matchKind}`, label: t(MATCH_KIND_KEY[question.matchKind]), tone: slotTone.matchKind, order: QUESTION_SLOT_ORDER.matchKind },
  ];
  return pills.sort(byOrder);
}

/** A run scored with a stand-in adapter says nothing about a real model, and needs reading as such. */
export function presentRun(isMock: boolean, t: Translate): PresentedPill[] {
  return isMock ? [{ key: 'mock', label: t('console.evaluation.runs.mock'), tone: 'warning', order: 10 }] : [];
}

/** The languages the set actually holds, so the filter never offers an empty result. */
export function languageOptions(questions: readonly EvalQuestion[], languages: readonly { key: string; label: string }[] | undefined): { key: string; label: string }[] {
  return [...new Set(questions.map((question) => question.lang))].map((key) => ({ key, label: languageLabel(key, languages) })).sort((a, b) => a.label.localeCompare(b.label));
}

export const METRICS = [
  { key: 'recallAt10', labelKey: 'console.evaluation.metric.recallAt10' },
  { key: 'mrr', labelKey: 'console.evaluation.metric.mrr' },
] as const satisfies readonly { key: keyof EvalScores & keyof EvalBaseline; labelKey: MessageKey }[];

/** A score from 0 to 1 in the reader's locale. */
export function formatScore(value: number, ctx: FormatContext): string {
  return new Intl.NumberFormat(localeTags[ctx.locale], { minimumFractionDigits: 2, maximumFractionDigits: 3 }).format(value);
}

/** A baseline score, or "Unrecorded": null is the absence of a score and never reads as zero. */
export function formatBaseline(value: number | null, t: Translate, ctx: FormatContext): string {
  return value === null ? t('console.evaluation.baseline.unrecorded') : formatScore(value, ctx);
}
