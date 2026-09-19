import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { Chip, ChipRow } from './Chip';
import { Notice } from './Notice';
import { Swatch, SwatchPair } from './Swatch';
import { TabPanel, Tabs } from './Tabs';

// The primitives the vocabulary and footprint cards need
// (design/screens/admin-vocabulary.html, admin-footprint.html).

describe('Swatch', () => {
  it('pins a theme by class so the pill inside renders in it whatever the viewer chose', () => {
    const { container } = render(<Swatch scheme="dark">{'x'}</Swatch>);
    const swatch = container.querySelector('[data-swatch="dark"]');
    expect(swatch?.classList.contains('dark')).toBe(true);
  });

  it('shows a value once in light and once in dark', () => {
    const { container } = render(<SwatchPair>{'Custody'}</SwatchPair>);
    expect([...container.querySelectorAll('[data-swatch]')].map((el) => el.getAttribute('data-swatch'))).toEqual(['light', 'dark']);
    expect(screen.getAllByText('Custody')).toHaveLength(2);
  });
});

describe('Tabs', () => {
  it('marks the current tab, wires it to its panel and reports a selection', () => {
    const onSelect = vi.fn();
    render(
      <>
        <Tabs current="ours" onSelect={onSelect} tabs={[{ id: 'ours', label: 'Our lists' }, { id: 'library', label: 'Shared library lists', badge: '7' }]} />
        <TabPanel id="ours">{'panel'}</TabPanel>
      </>,
    );
    const ours = screen.getByRole('tab', { name: 'Our lists' });
    expect(ours.getAttribute('aria-selected')).toBe('true');
    expect(ours.getAttribute('aria-controls')).toBe('panel-ours');
    expect(screen.getByRole('tabpanel').getAttribute('aria-labelledby')).toBe('tab-ours');
    const library = screen.getByRole('tab', { name: /Shared library lists/ });
    expect(library.getAttribute('aria-selected')).toBe('false');
    expect(library.textContent).toContain('7');
    fireEvent.click(library);
    expect(onSelect).toHaveBeenCalledWith('library');
  });
});

describe('Chip', () => {
  it('reports pressed, struck and disabled, and forwards clicks', () => {
    const onClick = vi.fn();
    render(
      <ChipRow>
        <Chip pressed onClick={onClick}>
          {'Advice'}
        </Chip>
        <Chip pressed struck disabled>
          {'Tax'}
        </Chip>
        <Chip pressed={false}>{'Custody'}</Chip>
      </ChipRow>,
    );
    const advice = screen.getByRole('button', { name: 'Advice' });
    expect(advice.getAttribute('aria-pressed')).toBe('true');
    expect(advice.hasAttribute('data-struck')).toBe(false);
    fireEvent.click(advice);
    expect(onClick).toHaveBeenCalledTimes(1);
    const tax = screen.getByRole('button', { name: 'Tax' });
    expect(tax.hasAttribute('data-struck')).toBe(true);
    expect((tax as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByRole('button', { name: 'Custody' }).getAttribute('aria-pressed')).toBe('false');
  });
});

describe('Notice', () => {
  it('announces a refusal as an alert and anything else as status', () => {
    render(
      <>
        <Notice tone="bad">{'You requested this change.'}</Notice>
        <Notice tone="warn">{'Waiting'}</Notice>
        <Notice>{'Read only'}</Notice>
      </>,
    );
    expect(screen.getByRole('alert').textContent).toBe('You requested this change.');
    expect(screen.getAllByRole('status').map((el) => el.getAttribute('data-notice'))).toEqual(['warn', 'plain']);
  });

  it('passes other attributes through, so a screen can hook the banner of one record', () => {
    render(
      <Notice tone="warn" data-pending-request="r1" aria-label="Pending change" className="grid">
        {'Waiting'}
      </Notice>,
    );
    const banner = screen.getByRole('status', { name: 'Pending change' });
    expect(banner.getAttribute('data-pending-request')).toBe('r1');
    expect(banner.getAttribute('data-notice')).toBe('warn');
    expect(banner.classList.contains('grid')).toBe(true);
  });
});
