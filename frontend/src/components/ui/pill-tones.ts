// The ONLY place the pill tones are listed (playbook 6.7,
// design/system/pills-and-labels.md). Six tones, named as Green names them:
// `information` is the grey one and `notice` is blue. There is no seventh,
// and no component accepts a colour. Token pairs are copied from the card's
// table exactly; `brand` is overridden in brand.css. In dark the four status
// tones take Green's `-03` background step: at `-02` dark `negative` is
// 4.47:1 and fails AA (pills-and-labels.md, 2026-09-19). Light is unchanged.
//
// ESLint forbids importing this file outside components/ui, features/shared
// and features/**/*-presentation.ts, so a screen can never pick a tone.

export const pillTones = {
  information: { background: '--gds-sys-color-l3-neutral-02', darkBackground: '--gds-sys-color-l3-neutral-02', text: '--gds-sys-color-content-neutral-01' },
  notice: { background: '--gds-sys-color-l3-notice-02', darkBackground: '--gds-sys-color-l3-notice-03', text: '--gds-sys-color-content-notice-01' },
  positive: { background: '--gds-sys-color-l3-positive-02', darkBackground: '--gds-sys-color-l3-positive-03', text: '--gds-sys-color-content-positive-03' },
  warning: { background: '--gds-sys-color-l3-warning-02', darkBackground: '--gds-sys-color-l3-warning-03', text: '--gds-sys-color-content-warning-01' },
  negative: { background: '--gds-sys-color-l3-negative-02', darkBackground: '--gds-sys-color-l3-negative-03', text: '--gds-sys-color-content-negative-01' },
  brand: { background: '--gds-sys-color-l3-brand-02', darkBackground: '--gds-sys-color-l3-brand-02', text: '--gds-sys-color-content-brand-02' },
} as const;

export type PillTone = keyof typeof pillTones;

export const pillToneNames = Object.keys(pillTones) as readonly PillTone[];
