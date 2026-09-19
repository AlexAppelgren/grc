// Rail icons keyed by destination id: small stroke icons on currentColor,
// seb.io's "small icon plus a label". The first four are the prototype's own.
// A destination without an icon here gets a quiet dot, so the collapsed rail
// never shows an empty square when the registry adds one.
const ICONS: Record<string, readonly string[]> = {
  today: ['M4 11l8-7 8 7v9H4z'],
  watch: ['M12 12m-3 0a3 3 0 1 0 6 0a3 3 0 1 0-6 0', 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z'],
  inventory: ['M5 4h11l3 3v13H5z', 'M8 10h8M8 14h8'],
  search: ['M11 11m-6 0a6 6 0 1 0 12 0a6 6 0 1 0-12 0', 'M20 20l-4-4'],
  roadmap: ['M4 6h16v14H4z', 'M4 10h16', 'M8 3v4M16 3v4'],
  admin: ['M4 7h9M17 7h3M4 17h3M11 17h9', 'M15 7m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0', 'M9 17m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0'],
  'console-queue': ['M4 13l2-8h12l2 8v6H4z', 'M4 13h5l1 2h4l1-2h5'],
  'console-vocabularies': ['M9 6h11M9 12h11M9 18h11', 'M5 6h.01M5 12h.01M5 18h.01'],
  'console-sources': ['M12 12m-8 0a8 8 0 1 0 16 0a8 8 0 1 0-16 0', 'M4 12h16', 'M12 4c2.5 2.2 2.5 13.8 0 16M12 4c-2.5 2.2-2.5 13.8 0 16'],
  account: ['M12 8m-3.5 0a3.5 3.5 0 1 0 7 0a3.5 3.5 0 1 0-7 0', 'M5 20c1.2-3.5 4-5 7-5s5.8 1.5 7 5'],
  'sidebar-collapse': ['M4 5h16v14H4z', 'M9 5v14', 'M15 10l-2 2 2 2'],
  'sidebar-expand': ['M4 5h16v14H4z', 'M9 5v14', 'M13 10l2 2-2 2'],
};

const DOT: readonly string[] = ['M12 12m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0'];

export function NavIcon({ id }: { id: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="size-4 shrink-0 fill-none stroke-current stroke-[1.75] [stroke-linecap:round] [stroke-linejoin:round]">
      {(ICONS[id] ?? DOT).map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}
