import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { Checkbox } from './checkbox';

// The Radix checkbox in our colours: its three states, the press that asks for
// the next one, and the row around it, which a press on the box never reaches,
// so a row that is itself a link is not followed. Copy is English.

afterEach(() => {
  vi.unstubAllGlobals();
});

const box = () => screen.getByRole('checkbox');
/** The mark drawn in the box: the tick, the bar, or nothing. */
const mark = () => box().querySelector('path')?.getAttribute('d') ?? null;

const TICK = 'M4.5 8.2l2.4 2.4 4.6-5';
const BAR = 'M4.5 8h7';

describe('Checkbox', () => {
  it('is empty when unchecked, and a press asks to tick it', () => {
    const onCheckedChange = vi.fn();
    render(<Checkbox checked={false} onCheckedChange={onCheckedChange} aria-label="Select the duty" />);
    const checkbox = screen.getByRole('checkbox', { name: 'Select the duty' });
    expect(checkbox).toHaveAttribute('type', 'button');
    expect(checkbox).not.toBeChecked();
    expect(mark()).toBeNull();
    fireEvent.click(checkbox);
    expect(onCheckedChange).toHaveBeenCalledExactlyOnceWith(true);
    // The caller holds the state: nothing changes until it says so.
    expect(checkbox).not.toBeChecked();
  });

  it('draws the tick when checked, and a press asks to empty it', () => {
    const onCheckedChange = vi.fn();
    render(<Checkbox checked onCheckedChange={onCheckedChange} aria-label="Select the duty" />);
    expect(box()).toBeChecked();
    expect(mark()).toBe(TICK);
    expect(box().querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
    fireEvent.click(box());
    expect(onCheckedChange).toHaveBeenCalledExactlyOnceWith(false);
  });

  it('draws the bar when some of a set are ticked, and a press asks to tick them all', () => {
    const onCheckedChange = vi.fn();
    render(<Checkbox checked="indeterminate" onCheckedChange={onCheckedChange} aria-label="Select every duty" />);
    expect(box()).toBePartiallyChecked();
    expect(mark()).toBe(BAR);
    fireEvent.click(box());
    expect(onCheckedChange).toHaveBeenCalledExactlyOnceWith(true);
  });

  it('follows the state the caller holds', () => {
    const { rerender } = render(<Checkbox checked={false} aria-label="Select the duty" />);
    // Nobody listens: a press changes nothing and breaks nothing.
    fireEvent.click(box());
    expect(box()).not.toBeChecked();
    rerender(<Checkbox checked aria-label="Select the duty" />);
    expect(box()).toBeChecked();
    rerender(<Checkbox checked="indeterminate" aria-label="Select the duty" />);
    expect(box()).toBePartiallyChecked();
  });

  it('cannot be pressed when disabled', () => {
    const onCheckedChange = vi.fn();
    render(<Checkbox checked disabled onCheckedChange={onCheckedChange} aria-label="Select the duty" />);
    expect(box()).toBeDisabled();
    expect(box().className).toContain('disabled:opacity-50');
    fireEvent.click(box());
    expect(onCheckedChange).not.toHaveBeenCalled();
  });

  it('takes its name from the caller: a label, the text of another element, or a label element on its id', () => {
    render(
      <>
        <Checkbox checked={false} aria-label="By label" />
        <span id="title">By another element</span>
        <Checkbox checked={false} aria-labelledby="title" />
        <label htmlFor="terms">By a label element</label>
        <Checkbox id="terms" checked={false} />
      </>,
    );
    expect(screen.getByRole('checkbox', { name: 'By label' })).toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: 'By another element' })).toBeInTheDocument();
    expect(screen.getByLabelText('By a label element')).toHaveAttribute('id', 'terms');
  });

  it('is a 20px box in token colours with 4px corners, and a 44px target on a touch screen', () => {
    const { rerender } = render(<Checkbox checked={false} aria-label="Select the duty" className="mt-1" data-select="art-25" />);
    const empty = box().className;
    for (const token of ['size-5', 'rounded-[4px]', 'border-line-strong', 'bg-surface', 'mt-1']) expect(empty).toContain(token);
    expect(empty).not.toContain('bg-button');
    expect(empty).not.toContain('rounded-full');
    // 44px centred on the box, drawn by a pseudo-element so the row's layout stays as it is.
    for (const token of ['relative', 'pointer-coarse:after:absolute', 'pointer-coarse:after:top-1/2', 'pointer-coarse:after:left-1/2', 'pointer-coarse:after:size-11', 'pointer-coarse:after:-translate-1/2']) {
      expect(empty).toContain(token);
    }
    // A hook the screen sets reaches the button.
    expect(box()).toHaveAttribute('data-select', 'art-25');

    rerender(<Checkbox checked aria-label="Select the duty" />);
    for (const token of ['border-button', 'bg-button', 'text-on-button']) expect(box().className).toContain(token);
    expect(box().className).not.toContain('bg-surface');
    rerender(<Checkbox checked="indeterminate" aria-label="Select the duty" />);
    expect(box().className).toContain('bg-button');
  });

  it('never presses or follows the row it sits in, while the rest of the row stays the link', () => {
    const onRow = vi.fn();
    const onCheckedChange = vi.fn();
    render(
      <a href="#duty" onClick={onRow}>
        <Checkbox checked={false} onCheckedChange={onCheckedChange} aria-label="Select the duty" />
        Record keeping
      </a>,
    );
    // fireEvent answers false when the event was cancelled, which is what stops a browser following the link.
    expect(fireEvent.click(box())).toBe(false);
    expect(onCheckedChange).toHaveBeenCalledExactlyOnceWith(true);
    expect(onRow).not.toHaveBeenCalled();

    expect(fireEvent.click(screen.getByText('Record keeping'))).toBe(true);
    expect(onRow).toHaveBeenCalledOnce();
  });

  it('keeps a change made inside a form from reaching the row', () => {
    // In a form Radix mirrors the state in a hidden input, sized to the box, and reports each change with a click from it.
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe(): void {}
        unobserve(): void {}
        disconnect(): void {}
      },
    );
    const onRow = vi.fn();
    const row = (checked: boolean) => (
      <form>
        <a href="#duty" onClick={onRow}>
          <Checkbox checked={checked} aria-label="Select the duty" />
        </a>
      </form>
    );
    const { container, rerender } = render(row(false));
    const mirror = container.querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(mirror.checked).toBe(false);

    expect(fireEvent.click(box())).toBe(false);
    rerender(row(true));
    expect(mirror.checked).toBe(true);
    // And a change nobody pressed for, as a select-all makes.
    rerender(row(false));
    expect(mirror.checked).toBe(false);
    expect(onRow).not.toHaveBeenCalled();
  });
});
