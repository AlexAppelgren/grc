import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Pill, pillToneNames } from './Pill';
import { pillTones } from './pill-tones';
import { PillRow } from './PillRow';

describe('Pill (playbook 6.7)', () => {
  it('lists exactly six tones, named as Green names them', () => {
    expect([...pillToneNames]).toEqual(['information', 'notice', 'positive', 'warning', 'negative', 'brand']);
  });

  it.each(pillToneNames)('%s renders the token pair from the card as background and text', (tone) => {
    render(<Pill tone={tone}>label</Pill>);
    const pill = screen.getByText('label');
    expect(pill).toHaveAttribute('data-pill', tone);
    expect(pill.style.background).toBe(`light-dark(var(${pillTones[tone].background}), var(${pillTones[tone].darkBackground}))`);
    expect(pill.style.color).toBe(`var(${pillTones[tone].text})`);
    expect(pill).not.toHaveAttribute('data-outlined');
  });

  it('uses the card token names exactly, with the -03 dark step for the four status tones', () => {
    expect(pillTones.information).toEqual({ background: '--gds-sys-color-l3-neutral-02', darkBackground: '--gds-sys-color-l3-neutral-02', text: '--gds-sys-color-content-neutral-01' });
    expect(pillTones.notice).toEqual({ background: '--gds-sys-color-l3-notice-02', darkBackground: '--gds-sys-color-l3-notice-03', text: '--gds-sys-color-content-notice-01' });
    expect(pillTones.positive).toEqual({ background: '--gds-sys-color-l3-positive-02', darkBackground: '--gds-sys-color-l3-positive-03', text: '--gds-sys-color-content-positive-03' });
    expect(pillTones.warning).toEqual({ background: '--gds-sys-color-l3-warning-02', darkBackground: '--gds-sys-color-l3-warning-03', text: '--gds-sys-color-content-warning-01' });
    expect(pillTones.negative).toEqual({ background: '--gds-sys-color-l3-negative-02', darkBackground: '--gds-sys-color-l3-negative-03', text: '--gds-sys-color-content-negative-01' });
    expect(pillTones.brand).toEqual({ background: '--gds-sys-color-l3-brand-02', darkBackground: '--gds-sys-color-l3-brand-02', text: '--gds-sys-color-content-brand-02' });
  });

  it('renders a tenant tag outlined: transparent with the text colour as a ring', () => {
    render(
      <Pill tone="information" outlined>
        tag
      </Pill>,
    );
    const pill = screen.getByText('tag');
    expect(pill).toHaveAttribute('data-outlined', '');
    expect(pill.style.background).toBe('transparent');
    expect(pill.style.boxShadow).toContain(`var(${pillTones.information.text})`);
  });

  it('has the foundations shape: fully rounded, 20px, 8px sides, meta at 500', () => {
    render(<Pill tone="brand">LVM</Pill>);
    const pill = screen.getByText('LVM');
    expect(pill.className).toContain('rounded-full');
    expect(pill.className).toContain('h-5');
    expect(pill.className).toContain('px-2');
    expect(pill.className).toContain('font-medium');
    expect(pill.className).toContain('text-meta');
  });
});

describe('PillRow', () => {
  it('renders presented pills in order with their outline flag', () => {
    render(
      <PillRow
        pills={[
          { key: 'b', label: 'second', tone: 'notice', order: 2 },
          { key: 'a', label: 'first', tone: 'brand', order: 1, outlined: true },
        ]}
      >
        <span>meta</span>
      </PillRow>,
    );
    const pills = screen.getAllByText(/first|second/);
    expect(pills.map((p) => p.textContent)).toEqual(['second', 'first']);
    expect(screen.getByText('first')).toHaveAttribute('data-outlined', '');
    expect(screen.getByText('meta')).toBeInTheDocument();
  });
});
