import { act, fireEvent, render, screen } from '@testing-library/react';
import { renderToString } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
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
  SidebarTrigger,
  useSidebar,
} from './sidebar';

// The shadcn Sidebar parts the shell renders: collapse to icons and back,
// ctrl/cmd+b, the open state surviving a remount, tooltips only while
// collapsed, and the off-canvas sheet at phone width. Copy is English.

type Listener = () => void;
let mobile = false;
const mediaListeners = new Set<Listener>();

beforeEach(() => {
  mobile = false;
  mediaListeners.clear();
  window.localStorage.clear();
  vi.stubGlobal('matchMedia', () => ({
    get matches() {
      return mobile;
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
  const { state, openMobile, isMobile } = useSidebar();
  return <output data-testid="state" data-state={state} data-open-mobile={String(openMobile)} data-mobile={String(isMobile)} />;
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
        <SidebarTrigger />
        <State />
      </SidebarInset>
    </SidebarProvider>,
  );
}

const state = () => screen.getByTestId('state');
const trigger = () => screen.getByRole('button', { name: 'Toggle the menu' });
const rail = () => document.querySelector('[data-slot="sidebar"]');
const ctrlB = () => fireEvent.keyDown(window, { key: 'b', ctrlKey: true });

describe('SidebarProvider', () => {
  it('refuses to run outside a provider', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<State />)).toThrow('useSidebar must be used inside a <SidebarProvider>.');
  });

  it('starts expanded, sets the width variables, and the trigger collapses it to icons and back', () => {
    const { container } = renderRail();
    const wrapper = container.querySelector('[data-slot="sidebar-wrapper"]') as HTMLElement;
    expect(wrapper.style.getPropertyValue('--sidebar-width')).toBe('15rem');
    expect(wrapper.style.getPropertyValue('--sidebar-width-icon')).toBe('3rem');
    expect(wrapper.style.getPropertyValue('--sidebar-width-mobile')).toBe('17.5rem');
    expect(rail()).toHaveAttribute('data-collapsible', '');

    fireEvent.click(trigger());
    expect(state()).toHaveAttribute('data-state', 'collapsed');
    expect(rail()).toHaveAttribute('data-collapsible', 'icon');

    fireEvent.click(trigger());
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

  it('renders expanded and desktop on the server, never reading storage or the viewport', () => {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, 'false');
    mobile = true;
    const html = renderToString(
      <SidebarProvider>
        <State />
      </SidebarProvider>,
    );
    expect(html).toContain('data-state="expanded"');
    expect(html).toContain('data-mobile="false"');
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

describe('at phone width', () => {
  it('becomes an off-canvas sheet the trigger and the shortcut open and close', () => {
    renderRail();
    mobile = true;
    act(() => mediaListeners.forEach((l) => l()));
    expect(state()).toHaveAttribute('data-mobile', 'true');
    expect(screen.queryByRole('dialog')).toBeNull();

    fireEvent.click(trigger());
    const sheet = screen.getByRole('dialog', { name: 'Navigation' });
    expect(sheet).toHaveTextContent('Today');
    // The desktop state is untouched by the sheet.
    expect(state()).toHaveAttribute('data-state', 'expanded');

    ctrlB();
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(state()).toHaveAttribute('data-open-mobile', 'false');
  });

  it('never shows a tooltip in the sheet, even when the desktop rail was collapsed', () => {
    window.localStorage.setItem(SIDEBAR_STORAGE_KEY, 'false');
    mobile = true;
    renderRail();
    fireEvent.click(trigger());
    fireEvent.focus(screen.getByRole('button', { name: 'Today' }));
    expect(screen.queryByRole('tooltip')).toBeNull();
  });
});
