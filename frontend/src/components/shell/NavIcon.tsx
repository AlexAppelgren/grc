// Navigation icons keyed by destination id, plus the few controls that share
// them (close, filters): small stroke icons on currentColor, seb.io's "small
// icon plus a label". Today, Watch, Inventory and Ask were redrawn with the tab
// bar (Alex, 2026-10-03: modern, not old school), each with a solid form the
// current tab shows: the same shape filled in, so the state reads in the
// icon's shape and not in colour alone (WCAG 1.4.1). A destination without an
// icon here gets a quiet dot, so the collapsed rail never shows an empty
// square when the registry adds one. 16px in a rail or sheet row, 20px over a
// tab's label (design/system/navigation.md 5).
const HOME = 'M3.5 10.2 12 3.5l8.5 6.7V19a1.5 1.5 0 0 1-1.5 1.5h-4v-5.5H9v5.5H5A1.5 1.5 0 0 1 3.5 19z';
const EYE = 'M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z';
const PUPIL = 'M12 12m-2.75 0a2.75 2.75 0 1 0 5.5 0a2.75 2.75 0 1 0-5.5 0';
const LAYERS = ['M12 3.5 3.5 8 12 12.5 20.5 8z', 'm3.5 12 8.5 4.5 8.5-4.5', 'm3.5 16 8.5 4.5 8.5-4.5'] as const;
const BUBBLE = 'M20.5 11.5a8 8 0 0 1-11.8 7L4 19.8l1.3-4.4A8 8 0 1 1 20.5 11.5z';

const ICONS: Record<string, readonly string[]> = {
  today: [HOME],
  watch: [PUPIL, EYE],
  inventory: LAYERS,
  search: ['M11 11m-6 0a6 6 0 1 0 12 0a6 6 0 1 0-12 0', 'M20 20l-4-4'],
  ask: [BUBBLE],
  roadmap: ['M4 6h16v14H4z', 'M4 10h16', 'M8 3v4M16 3v4'],
  // c8-ui-gaps-risk: where the bank falls short, a warning triangle.
  gaps: ['M12 4l9 16H3z', 'M12 10v4', 'M12 17h.01'],
  'my-work': ['M9 6h11M9 12h11M9 18h11', 'M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2'],
  admin: ['M4 7h9M17 7h3M4 17h3M11 17h9', 'M15 7m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0', 'M9 17m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0'],
  'console-queue': ['M4 13l2-8h12l2 8v6H4z', 'M4 13h5l1 2h4l1-2h5'],
  'console-vocabularies': ['M9 6h11M9 12h11M9 18h11', 'M5 6h.01M5 12h.01M5 18h.01'],
  'console-sources': ['M12 12m-8 0a8 8 0 1 0 16 0a8 8 0 1 0-16 0', 'M4 12h16', 'M12 4c2.5 2.2 2.5 13.8 0 16M12 4c-2.5 2.2-2.5 13.8 0 16'],
  // Drawn ahead of its page, so the task that registers it leaves the shell alone.
  'console-tenants': ['M4 20h16', 'M6 20V5h8v15', 'M14 9h4v11', 'M9 8h2M9 12h2M9 16h2'],
  account: ['M12 8m-3.5 0a3.5 3.5 0 1 0 7 0a3.5 3.5 0 1 0-7 0', 'M5 20c1.2-3.5 4-5 7-5s5.8 1.5 7 5'],
  'sidebar-collapse': ['M4 5h16v14H4z', 'M9 5v14', 'M15 10l-2 2 2 2'],
  'sidebar-expand': ['M4 5h16v14H4z', 'M9 5v14', 'M13 10l2 2-2 2'],
  more: ['M5 12m-1.5 0a1.5 1.5 0 1 0 3 0a1.5 1.5 0 1 0-3 0', 'M12 12m-1.5 0a1.5 1.5 0 1 0 3 0a1.5 1.5 0 1 0-3 0', 'M19 12m-1.5 0a1.5 1.5 0 1 0 3 0a1.5 1.5 0 1 0-3 0'],
  close: ['M6 6l12 12M18 6L6 18'],
  filters: ['M4 7h9M17 7h3M4 17h3M11 17h9', 'M15 7m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0', 'M9 17m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0'],
};

// The solid forms: [path, 'fill' | 'line']. The eye is one path, so its pupil
// stays a hole under the even-odd rule.
const SOLID: Record<string, readonly (readonly [string, 'fill' | 'line'])[]> = {
  today: [[HOME, 'fill']],
  watch: [[`${EYE} ${PUPIL}`, 'fill']],
  inventory: [
    [LAYERS[0], 'fill'],
    [LAYERS[1], 'line'],
    [LAYERS[2], 'line'],
  ],
  ask: [[BUBBLE, 'fill']],
};

const SIZE = { row: 'size-4', tab: 'size-5' } as const;

const DOT: readonly string[] = ['M12 12m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0'];

export function NavIcon({ id, size = 'row', solid = false }: { id: string; size?: keyof typeof SIZE; solid?: boolean }) {
  const paths = (solid ? SOLID[id] : undefined) ?? (ICONS[id] ?? DOT).map((d) => [d, 'line'] as const);
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={`${SIZE[size]} shrink-0 fill-none stroke-current stroke-[1.75] [stroke-linecap:round] [stroke-linejoin:round]`}>
      {paths.map(([d, kind]) => (
        <path key={d} d={d} fill={kind === 'fill' ? 'currentColor' : undefined} fillRule={kind === 'fill' ? 'evenodd' : undefined} />
      ))}
    </svg>
  );
}
