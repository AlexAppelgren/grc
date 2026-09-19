import { Pill } from '@/components/ui/Pill';
import type { PresentedPill } from '@/features/shared/presentation-types';

// Renders what a presentation function returned, in its order. The one
// place a PresentedPill becomes a Pill.
export function PillRow({ pills, children }: { pills: readonly PresentedPill[]; children?: React.ReactNode }) {
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      {pills.map((pill) => (
        <Pill key={pill.key} tone={pill.tone} outlined={pill.outlined}>
          {pill.label}
        </Pill>
      ))}
      {children}
    </span>
  );
}
