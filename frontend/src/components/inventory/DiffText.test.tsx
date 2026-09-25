import { render } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';

import { DiffText, type DiffSegment } from './DiffText';

const segments: DiffSegment[] = [
  { op: 'equal', text: 'Research may be received only if it is paid from own resources.' },
  { op: 'delete', text: 'No assessment is required.' },
  { op: 'insert', text: 'The institution sets criteria for an annual assessment.' },
  { op: 'equal', text: 'The rules apply.' },
];

function renderIn(locale: 'en' | 'sv', node: ReactNode) {
  return render(<LocaleProvider locale={locale}>{node}</LocaleProvider>);
}

describe('DiffText', () => {
  it('marks an added sentence as ins on positive-soft and a removed one as del on negative-soft', () => {
    const { container } = renderIn('en', <DiffText segments={segments} />);
    const ins = container.querySelectorAll('ins');
    const del = container.querySelectorAll('del');
    expect(ins).toHaveLength(1);
    expect(del).toHaveLength(1);
    expect(ins[0]).toHaveClass('bg-positive-soft', 'text-fg');
    expect(del[0]).toHaveClass('bg-negative-soft', 'text-fg');
    expect(ins[0]).toHaveTextContent('The institution sets criteria for an annual assessment.');
    expect(del[0]).toHaveTextContent('No assessment is required.');
  });

  it('tells a screen reader where an addition or a removal starts and ends', () => {
    const { container } = renderIn('en', <DiffText segments={segments} />);
    const ins = container.querySelector('ins');
    const del = container.querySelector('del');
    expect([...(ins?.querySelectorAll('.sr-only') ?? [])].map((n) => n.textContent?.trim())).toEqual(['Added text:', 'End of added text.']);
    expect([...(del?.querySelectorAll('.sr-only') ?? [])].map((n) => n.textContent?.trim())).toEqual(['Removed text:', 'End of removed text.']);
  });

  it('keeps the order and separates sentences by a space', () => {
    const { container } = renderIn('en', <DiffText segments={segments} />);
    container.querySelectorAll('.sr-only').forEach((n) => n.remove());
    expect(container.textContent).toBe(
      'Research may be received only if it is paid from own resources. No assessment is required. The institution sets criteria for an annual assessment. The rules apply.',
    );
  });

  it('reads the markers in the user language', () => {
    const { container } = renderIn('sv', <DiffText segments={segments} />);
    expect(container.querySelector('ins .sr-only')).toHaveTextContent('Tillagd text:');
    expect(container.querySelector('del .sr-only')).toHaveTextContent('Borttagen text:');
  });

  it('an unchanged text renders with no marks', () => {
    const { container } = renderIn('en', <DiffText segments={[{ op: 'equal', text: 'Only this.' }]} />);
    expect(container.querySelector('ins, del')).toBeNull();
    expect(container.textContent).toBe('Only this.');
  });
});
