// Dock icons from the prototype, keyed by destination id. Stroke icons on
// currentColor; a destination without one shows no icon.
const ICONS: Record<string, string[]> = {
  today: ['M4 11l8-7 8 7v9H4z'],
  watch: ['M12 12m-3 0a3 3 0 1 0 6 0a3 3 0 1 0-6 0', 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z'],
  inventory: ['M5 4h11l3 3v13H5z', 'M8 10h8M8 14h8'],
  search: ['M11 11m-6 0a6 6 0 1 0 12 0a6 6 0 1 0-12 0', 'M20 20l-4-4'],
  more: ['M5 12m-1.5 0a1.5 1.5 0 1 0 3 0a1.5 1.5 0 1 0-3 0', 'M12 12m-1.5 0a1.5 1.5 0 1 0 3 0a1.5 1.5 0 1 0-3 0', 'M19 12m-1.5 0a1.5 1.5 0 1 0 3 0a1.5 1.5 0 1 0-3 0'],
};

export function NavIcon({ id }: { id: string }) {
  const paths = ICONS[id];
  if (paths === undefined) return null;
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="h-[22px] w-[22px] fill-none stroke-current stroke-[1.7] [stroke-linecap:round] [stroke-linejoin:round]">
      {paths.map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
}
