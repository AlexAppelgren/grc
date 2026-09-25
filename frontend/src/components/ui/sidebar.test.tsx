import { act, fireEvent, render, screen } from '@testing-library/react';
import { renderToString } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  COMPACT_QUERY,
  readStoredOpen,
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SIDEBAR_STORAGE_KEY,
  useSidebar,
} from './sidebar';

// The shadcn Sidebar parts the shell renders: collapse to icons and back,
// ctrl/cmd+b, the open state surviving a remount, and tooltips only while
// collapsed. Below 1024 px the rail stays in the page, hidden by CSS, and the
// tab bar takes over (design/system/navigation.md). Copy is English.

type Listener = () => void;
let compact = false;
const mediaListeners = new Set<Listener>();

beforeEach(() => {
  compact = false;
  mediaListeners.clear();
  window.localStorage.clear();
  // Only the compact query answers true, so a component asking anything else is caught.
  vi.stubGlobal('matchMedia', (query: string) => ({
    get matches() {
      return query === COMPACT_QUERY && compact;
    },
    addEventListener: (_: string, l: Listener) => mediaListeners.add(l),
    removeEventListener: (_: string, l: Listener) => mediaListeners.delete(l),
  }));
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    },
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function State() {
  const { state, isCompact } = useSidebar();
  return <output data-testid="state" data-state={state} data-compact={String(isCompact)} />;
}

function renderRail() {
  return render(
    <SidebarProvider>
      <Sidebar>
        <SidebarHeader>{'head'}</SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton isActive tooltip="Today">
                  <span>{'Today'}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter>{'foot'}</SidebarFooter>
      </Sidebar>
      <SidebarInset>
        <State />
      </SidebarInset>
    </SidebarProvider>,
  );
}

const state = () => screen.getByTestId('state');
const rail = () => document.querySelector('[data-slot="sidebar"]');
/** True when nothing called preventDefault, as dispatchEvent reports it. */
const ctrlB = () => fireEvent.keyDown(window, { key: 'b', ctrlKey: true });
const flipCompact = (value: boolean) => {
  compact = value;
  act(() => mediaListeners.forEach((l) => l()));
};

describe('SidebarProvider', () => {
  it('refuses to run outside a provider', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<State />)).toThrow('useSidebar must be used inside a <SidebarProvider>.');
  });

  it("switches navigation at 1024 px, the query Tailwind's lg: compiles to", () => {
    expect(COMPACT_QUERY).toBe('(width < 64rem)');
  });

  it('starts expanded, sets the width variables, and ctrl+b collapses it to icons and back', () => {
    const { container } = renderRail();
    const wrapper = container.querySelector('[data-slot="sidebar-wrapper"]') as HTMLElement;
    expect(wrapper.style.getPropertyValue('--sidebar-width')).toBe('15rem');
    expect(wrapper.style.getPropertyValue('--sidebar-width-icon')).toBe('3rem');
    // Stacks the page below 1024 px, so a static tab bar (very short windows) sits above main.
    expect(wrapper).toHaveClass('max-lg:flex-col');
    expect(rail()).toHaveAttribute('data-collapsible', '');
    expect(rail()).toHaveClass('hidden', 'lg:block');

    expect(ctrlB()).toBe(false);
    expect(state()).toHaveAttribute('data-state', 'collapsed');
    expect(rail()).toHaveAttribute('data-collapsible', 'icon');

    ctrlB();
    expect(state()).toHaveAttribute('data-state', 'expanded');
  });

  it('toggles on ctrl+b and cmd+b, and ignores b alone', () => {
    renderRail();
    ctrlB();
    expect(state()).toHaveAttribute('data-state', 'collapsed');
    fireEvent.keyDown(window, { key: 'b', metaKey: true });
    expect(state()).toHaveAttribute('data-state', 'expanded');
    fireEvent.keyDown(window, { key: 'b' });
    fireEvent.keyDown(window, { key: 'c', ctrlKey: true });
    expect(state()).toHaveAttribute('data-state', 'expanded');
  });

  it('remembers the open state across a remount', () => {
    const first = renderRail();
    ctrlB();
    expect(window.localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBe('false');
    first.unmount();

    renderRail();
    expect(state()).toHaveAttribute('data-state', 'collapsed');
  });

  it('follows a change made in another tab', () => {
    renderRail();
    act(() => {
      window.localStorage.setItem(SIDEBAR_STORAGE_KEY, 'false');
      window.dispatchEvent(new StorageEvent('storage', { key: SIDEBAR_STORAGE_KEY }));
    });
    expect(state()).toHaveAttribute('data-state', 'collapsed');
  });

  it('still toggles when storage throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('denied');
    });
    renderRail();
    expect(state()).toHaveAttribute('data-state', 'expanded');
    ctrlB();
    expect(state()).toHaveAttribute('data-state', 'collapsed');
  });

  it('reads only true and false from storage', () => {
    expect(readStoredOpen()).toBeNull();
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, 'true');
    expect(readStoredOpen()).toBe(true);
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, 'maybe');
    expect(readStoredOpen()).toBeNull();
  });

  it('renders expanded and wide on the server, never reading storage or the viewport', () => {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, 'false');
    compact = true;
    const html = renderToString(
      <SidebarProvider>
        <State />
      </SidebarProvider>,
    );
    expect(html).toContain('data-state="expanded"');
    expect(html).toContain('data-compact="false"');
  });

  it('drops its listeners on unmount', () => {
    const removed = vi.spyOn(window, 'removeEventListener');
    const view = renderRail();
    expect(mediaListeners.size).toBeGreaterThan(0);
    view.unmount();
    expect(mediaListeners.size).toBe(0);
    expect(removed.mock.calls.map(([type]) => type)).toEqual(expect.arrayContaining(['storage', 'keydown']));
  });
});

describe('SidebarMenuButton', () => {
  it('marks the current row with data-active, a small radius and medium weight, never a full pill', () => {
    renderRail();
    const button = screen.getByRole('button', { name: 'Today' });
    expect(button).toHaveAttribute('type', 'button');
    expect(button).toHaveAttribute('data-active', 'true');
    expect(button.className).toContain('rounded-md');
    expect(button.className).toContain('h-8');
    expect(button.className).toContain('data-[active=true]:font-medium');
    expect(button.className).not.toContain('rounded-full');
  });

  it('renders its child with asChild, and takes a size', () => {
    render(
      <SidebarProvider>
        <SidebarMenuButton asChild size="sm" tooltip="Watch">
          <a href="/watch">{'Watch'}</a>
        </SidebarMenuButton>
      </SidebarProvider>,
    );
    const link = screen.getByRole('link', { name: 'Watch' });
    expect(link).toHaveAttribute('data-active', 'false');
    expect(link).not.toHaveAttribute('type');
    expect(link.className).toContain('h-7');
  });

  it('shows its tooltip only while the rail is collapsed', async () => {
    renderRail();
    const today = screen.getByRole('button', { name: 'Today' });
    fireEvent.focus(today);
    expect(screen.queryByRole('tooltip')).toBeNull();
    fireEvent.blur(today);

    ctrlB();
    fireEvent.focus(today);
    expect(await screen.findByRole('tooltip')).toHaveTextContent('Today');
  });
});

describe('below 1024 px', () => {
  it('keeps the rail in the page for CSS to hide, never as a dialog, and leaves ctrl/cmd+b to the browser', () => {
    renderRail();
    flipCompact(true);
    expect(state()).toHaveAttribute('data-compact', 'true');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(rail()).toHaveClass('hidden', 'lg:block');

    // Nothing to toggle: the shortcut is neither handled nor prevented.
    expect(ctrlB()).toBe(true);
    expect(fireEvent.keyDown(window, { key: 'b', metaKey: true })).toBe(true);
    expect(state()).toHaveAttribute('data-state', 'expanded');
    expect(window.localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBeNull();

    flipCompact(false);
    expect(ctrlB()).toBe(false);
    expect(state()).toHaveAttribute('data-state', 'collapsed');
  });

  it('gives the More sheet a touch row: at least 44px tall, and a label that wraps instead of truncating', () => {
    render(
      <SidebarProvider>
        <SidebarMenuButton asChild size="touch" isActive tooltip="Roadmap">
          <a href="#roadmap">
            <span>{'Roadmap'}</span>
          </a>
        </SidebarMenuButton>
      </SidebarProvider>,
    );
    const row = screen.getByRole('link', { name: 'Roadmap' });
    expect(row.className).toContain('min-h-11');
    expect(row.className).toContain('text-body');
    expect(row.className).not.toContain('truncate');
    expect(row.className).not.toContain('overflow-hidden');
    expect(row.className).not.toContain('rounded-full');
    // The current row carries the tab bar's inset outline, which reaches 3:1.
    expect(row.className).toContain('outline-line-strong');
  });

  it('never shows a tooltip on a touch row, even when the stored rail state is collapsed', () => {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, 'false');
    compact = true;
    render(
      <SidebarProvider>
        <SidebarMenuButton size="touch" tooltip="Roadmap">
          <span>{'Roadmap'}</span>
        </SidebarMenuButton>
        <State />
      </SidebarProvider>,
    );
    expect(state()).toHaveAttribute('data-state', 'collapsed');
    fireEvent.focus(screen.getByRole('button', { name: 'Roadmap' }));
    expect(screen.queryByRole('tooltip')).toBeNull();

    flipCompact(false);
    fireEvent.focus(screen.getByRole('button', { name: 'Roadmap' }));
    expect(screen.queryByRole('tooltip')).toBeNull();
  });
});
