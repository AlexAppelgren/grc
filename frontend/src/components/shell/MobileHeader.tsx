'use client';

import { Logo } from '@/components/shell/Logo';

// Prototype `.mbrand`: the wordmark above the content on phones, where the
// side rail is hidden.
export function MobileHeader() {
  return (
    <div className="mb-3 md:hidden">
      <Logo className="block h-auto w-[150px] text-fg" />
    </div>
  );
}
