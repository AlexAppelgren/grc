import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { Fold } from './fold';

// A labelled disclosure on the Radix Collapsible: closed until asked, open on
// a press or when the caller says so, its content gone from the page while
// closed unless it is kept, and its trigger inside the heading the card
// needs. Copy is English.

const trigger = (name: string | RegExp = /Versions/) => screen.getByRole('button', { name });
const root = () => document.querySelector('[data-slot="fold"]') as HTMLElement;
const content = () => document.querySelector('[data-slot="fold-content"]') as HTMLElement;
const chevron = () => trigger().querySelector('svg') as SVGElement;

describe('Fold', () => {
  it('starts closed, with the content out of the page', () => {
    render(<Fold title="Versions">Version 1</Fold>);
    expect(trigger()).toHaveAttribute('type', 'button');
    expect(trigger()).toHaveAttribute('aria-expanded', 'false');
    expect(root()).toHaveAttribute('data-state', 'closed');
    expect(screen.queryByText('Version 1')).not.toBeInTheDocument();
    expect(chevron()).toHaveAttribute('aria-hidden', 'true');
    expect(chevron().getAttribute('class')).not.toContain('rotate-180');
  });

  it('opens on a press and closes on the next, the chevron turning with it', () => {
    render(<Fold title="Versions">Version 1</Fold>);
    fireEvent.click(trigger());
    expect(trigger()).toHaveAttribute('aria-expanded', 'true');
    expect(root()).toHaveAttribute('data-state', 'open');
    expect(screen.getByText('Version 1')).toBeVisible();
    // The button points at the region it opened.
    expect(trigger()).toHaveAttribute('aria-controls', content().id);
    expect(chevron().getAttribute('class')).toContain('rotate-180');

    fireEvent.click(trigger());
    expect(trigger()).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('Version 1')).not.toBeInTheDocument();
    expect(chevron().getAttribute('class')).not.toContain('rotate-180');
  });

  it('starts open when asked to', () => {
    render(
      <Fold title="Versions" defaultOpen>
        Version 1
      </Fold>,
    );
    expect(trigger()).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Version 1')).toBeVisible();
  });

  it('follows the caller when controlled: a press only asks', () => {
    const onOpenChange = vi.fn();
    const fold = (open: boolean) => (
      <Fold title="Versions" open={open} onOpenChange={onOpenChange} defaultOpen>
        Version 1
      </Fold>
    );
    const { rerender } = render(fold(false));
    // The caller's word wins over the starting state.
    expect(trigger()).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(trigger());
    expect(onOpenChange).toHaveBeenCalledExactlyOnceWith(true);
    expect(trigger()).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('Version 1')).not.toBeInTheDocument();

    rerender(fold(true));
    expect(trigger()).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('Version 1')).toBeVisible();

    fireEvent.click(trigger());
    expect(onOpenChange).toHaveBeenLastCalledWith(false);
    expect(trigger()).toHaveAttribute('aria-expanded', 'true');
  });

  it('keeps closed content in the page, hidden, when asked to', () => {
    render(
      <Fold title="Versions" keepMounted>
        Version 1
      </Fold>,
    );
    const kept = screen.getByText('Version 1');
    expect(kept).toBeInTheDocument();
    expect(kept).not.toBeVisible();
    expect(content()).toHaveAttribute('hidden');
    expect(content()).toHaveAttribute('data-state', 'closed');

    fireEvent.click(trigger());
    expect(content()).not.toHaveAttribute('hidden');
    expect(screen.getByText('Version 1')).toBeVisible();
    // The same node, never remounted.
    expect(screen.getByText('Version 1')).toBe(kept);

    fireEvent.click(trigger());
    expect(kept).toBeInTheDocument();
    expect(kept).not.toBeVisible();
  });

  it('shows a count muted after the title, in parentheses, and nothing without one', () => {
    const { rerender } = render(
      <Fold title="Versions" count={3}>
        Version 1
      </Fold>,
    );
    // A real space between the two, so the name reads and copies as two words.
    expect(trigger('Versions (3)').textContent).toBe('Versions (3)');
    expect(screen.getByText('(3)')).toHaveClass('text-muted');

    // None is still a count.
    rerender(
      <Fold title="Versions" count={0}>
        Version 1
      </Fold>,
    );
    expect(trigger('Versions (0)')).toBeInTheDocument();

    rerender(<Fold title="Versions">Version 1</Fold>);
    expect(trigger('Versions')).toBeInTheDocument();
    expect(trigger().textContent).toBe('Versions');
  });

  it('takes any node as its title', () => {
    render(
      <Fold title={<em>Earlier versions</em>} count={2}>
        Version 1
      </Fold>,
    );
    expect(trigger('Earlier versions (2)').querySelector('em')).toHaveTextContent('Earlier versions');
  });

  it('wraps the trigger in a plain element unless the card needs a heading there', () => {
    render(<Fold title="Versions">Version 1</Fold>);
    expect(screen.queryByRole('heading')).not.toBeInTheDocument();
    expect(trigger().parentElement?.tagName).toBe('DIV');
  });

  it.each([
    ['h2', 2],
    ['h3', 3],
  ] as const)('wraps the trigger in an %s when asked, and the row looks the same', (as, level) => {
    render(
      <Fold title="Versions" count={3} as={as}>
        Version 1
      </Fold>,
    );
    const heading = screen.getByRole('heading', { level, name: 'Versions (3)' });
    expect(heading).toContainElement(trigger());
    // The row sets its own size and weight, so a heading's do not reach it.
    for (const token of ['w-full', 'text-body', 'font-medium', 'tracking-normal']) expect(trigger().className).toContain(token);
  });

  it('draws a hairline above, and passes a screen its hooks on the root element', () => {
    render(
      <Fold title="Versions" data-versions-panel="" id="versions" className="mt-3">
        Version 1
      </Fold>,
    );
    expect(root()).toHaveAttribute('data-versions-panel', '');
    expect(root()).toHaveAttribute('id', 'versions');
    expect(root()).toHaveClass('border-t', 'border-line', 'mt-3');
    expect(root()).toContainElement(trigger());
  });
});
