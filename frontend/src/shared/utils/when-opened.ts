'use client';

import { useState } from 'react';

// A filter's list is read when its select is first reached, by pointer or by
// keyboard, rather than with the page: a screen that shows four filters no
// longer pays four reads before anyone looks at one. A value the address
// already names needs its label at once, so it reads straight away.

export interface OpenHandlers {
  onFocus: () => void;
  onPointerEnter: () => void;
}

/** Whether the list is wanted yet, and the handlers that say it now is. */
export function useWhenOpened(value: string): [boolean, OpenHandlers] {
  const [opened, setOpened] = useState(false);
  const open = () => setOpened(true);
  return [opened || value !== '', { onFocus: open, onPointerEnter: open }];
}
