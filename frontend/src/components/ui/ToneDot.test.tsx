import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { pillTones, pillToneNames } from './pill-tones';
import { ToneDot } from './ToneDot';

describe('ToneDot (design/screens/tenant-today.html)', () => {
  it.each(pillToneNames)('%s fills with the pill\'s own strong token, never a picked colour', (tone) => {
    const { container } = render(<ToneDot tone={tone} />);
    const dot = container.querySelector('i');
    expect(dot?.style.background).toBe(`var(${pillTones[tone].text})`);
  });
});
