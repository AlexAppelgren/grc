import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { Progress } from './progress';

// The Radix progress bar in our colours: how much of a whole is done, read out
// as a percentage and drawn as a share of the track, whatever the caller
// counts in. Copy is English.

afterEach(() => {
  vi.restoreAllMocks();
});

const bar = () => screen.getByRole('progressbar');
const fill = () => bar().firstElementChild as HTMLElement;

describe('Progress', () => {
  it('is empty at none', () => {
    render(<Progress value={0} max={12} aria-label="Duties answered" />);
    expect(screen.getByRole('progressbar', { name: 'Duties answered' })).toHaveAttribute('aria-valuenow', '0');
    expect(bar()).toHaveAttribute('aria-valuemin', '0');
    expect(bar()).toHaveAttribute('aria-valuemax', '100');
    expect(bar()).toHaveAttribute('aria-valuetext', '0%');
    expect(fill().style.width).toBe('0%');
  });

  it('fills the part done', () => {
    render(<Progress value={3} max={12} aria-label="Duties answered" />);
    expect(bar()).toHaveAttribute('aria-valuenow', '25');
    expect(bar()).toHaveAttribute('aria-valuetext', '25%');
    expect(bar()).toHaveAttribute('data-state', 'loading');
    expect(fill().style.width).toBe('25%');
  });

  it('is full at the whole', () => {
    render(<Progress value={12} max={12} aria-label="Duties answered" />);
    expect(bar()).toHaveAttribute('aria-valuenow', '100');
    expect(bar()).toHaveAttribute('data-state', 'complete');
    expect(fill().style.width).toBe('100%');
  });

  it.each([
    ['a count past its max reads as full', 15, 12, '100'],
    ['a count below none reads as empty', -2, 12, '0'],
    ['a whole of nothing reads as empty', 0, 0, '0'],
    ['a whole of nothing reads as empty whatever the count', 4, 0, '0'],
  ])('%s', (_, value, max, percent) => {
    // Radix refuses a value outside its range: it says so on the console and draws the bar as unknown.
    const refused = vi.spyOn(console, 'error').mockImplementation(() => {});
    render(<Progress value={value} max={max} aria-label="Duties answered" />);
    expect(bar()).toHaveAttribute('aria-valuenow', percent);
    expect(fill().style.width).toBe(`${percent}%`);
    expect(refused).not.toHaveBeenCalled();
  });

  it('reads the value as a percentage when no max is given', () => {
    render(<Progress value={40} aria-label="Duties answered" />);
    expect(bar()).toHaveAttribute('aria-valuenow', '40');
    expect(fill().style.width).toBe('40%');
  });

  it('takes its name from the caller, as a label or as the text of another element', () => {
    render(
      <>
        <span id="answered">Answered so far</span>
        <Progress value={3} max={12} aria-labelledby="answered" />
      </>,
    );
    expect(screen.getByRole('progressbar', { name: 'Answered so far' })).toBeInTheDocument();
  });

  it('is an 8px bar, fully rounded, in token colours', () => {
    render(<Progress value={3} max={12} aria-label="Duties answered" />);
    for (const token of ['h-2', 'w-full', 'overflow-hidden', 'rounded-full', 'bg-neutral-soft']) expect(bar().className).toContain(token);
    for (const token of ['h-full', 'rounded-full', 'bg-accent']) expect(fill().className).toContain(token);
  });

  it("passes a screen its hooks, and the value in the caller's own words", () => {
    render(<Progress value={3} max={12} aria-label="Duties answered" aria-valuetext="3 of 12" data-answered="" className="mt-2 w-40" />);
    expect(bar()).toHaveAttribute('data-answered', '');
    expect(bar()).toHaveAttribute('aria-valuetext', '3 of 12');
    expect(bar()).toHaveClass('mt-2', 'w-40');
    expect(bar().className).not.toContain('w-full');
  });
});
