import type { PillTone } from '@/components/ui/pill-tones';

// What the API sends: keys, kinds and facts, never a phrase (playbook 6.7).
// `label` is the vocabulary row's label in the user's language, resolved by
// the API from the row's translations.

export interface VocabularyRef {
  key: string;
  label: string;
}

export interface KindRef<K extends string> extends VocabularyRef {
  kind: K;
}

export interface PresentedPill {
  key: string;
  label: string;
  tone: PillTone;
  order: number;
  outlined?: boolean;
}

export function byOrder(a: PresentedPill, b: PresentedPill): number {
  return a.order - b.order;
}
