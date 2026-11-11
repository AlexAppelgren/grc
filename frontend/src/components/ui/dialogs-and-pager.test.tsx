import type { UseQueryResult } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';

import { ConfirmDialog, FormDialog } from './Dialogs';
import { Pager } from './Pager';
import { SecretOnce } from './SecretOnce';
import { QueryState } from './States';

const inEnglish = (node: ReactNode) => render(<LocaleProvider locale="en">{node}</LocaleProvider>);

describe('FormDialog', () => {
  it('submits once without the browser reloading, and never into a form it opens from', () => {
    const onSubmit = vi.fn();
    const outer = vi.fn((event: { preventDefault: () => void }) => event.preventDefault());
    inEnglish(
      <form onSubmit={outer}>
        <FormDialog title="Add a link" submitLabel="Link" pending={false} onSubmit={onSubmit} onClose={vi.fn()} formProps={{ 'data-link-dialog': 'pick' }}>
          <input aria-label="Name" />
        </FormDialog>
      </form>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Link' }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(outer).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog', { name: 'Add a link' }).querySelector('form[data-link-dialog="pick"]')).not.toBeNull();
  });

  it('holds its submit while pending or not ready, and shows a refusal in the screen\'s words', () => {
    const problem = Object.assign(new Error('refused'), { isAxiosError: true, response: { status: 409, data: { code: 'stale_write', detail: 'Changed.' } } });
    const { rerender } = inEnglish(<FormDialog title="Edit" submitLabel="Save" pending={false} submitDisabled onSubmit={vi.fn()} onClose={vi.fn()}>{null}</FormDialog>);
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    rerender(
      <LocaleProvider locale="en">
        <FormDialog title="Edit" submitLabel="Save" pending error={problem} codes={{ stale_write: 'Someone changed it.' }} onSubmit={vi.fn()} onClose={vi.fn()}>
          {null}
        </FormDialog>
      </LocaleProvider>,
    );
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
    expect(screen.getByRole('alert')).toHaveTextContent('Someone changed it.');
  });
});

describe('ConfirmDialog', () => {
  it('asks with its own way back and action, and closes on Escape as on the way back', () => {
    const onConfirm = vi.fn();
    const onClose = vi.fn();
    inEnglish(<ConfirmDialog title="Revoke key A?" body="It stops working at once." action="Revoke" cancelLabel="Keep it" danger busy={false} onConfirm={onConfirm} onClose={onClose} />);
    expect(screen.getByRole('dialog', { name: 'Revoke key A?' })).toHaveTextContent('It stops working at once.');
    fireEvent.click(screen.getByRole('button', { name: 'Revoke' }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: 'Keep it' }));
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('holds both buttons while the action runs and reads Cancel by default', () => {
    inEnglish(<ConfirmDialog title="Close the gap?" action="Close" busy onConfirm={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByRole('button', { name: 'Close' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeDisabled();
  });
});

describe('SecretOnce', () => {
  it('shows the secret once under its marker, copies it, and ends on Done', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    const onDone = vi.fn();
    const { container } = inEnglish(
      <SecretOnce secret="cwk_live_123" copyLabel="Copy key" onDone={onDone}>
        <p>Store it now.</p>
      </SecretOnce>,
    );
    expect(container.querySelector('[data-plain-key]')).toHaveTextContent('cwk_live_123');
    expect(container.querySelector('[data-feed-address]')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Copy key' }));
    expect(await screen.findByText('Copied.')).toBeInTheDocument();
    expect(writeText).toHaveBeenCalledWith('cwk_live_123');
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(onDone).toHaveBeenCalledTimes(1);
  });

  it('marks a calendar address as an address, and says nothing when the clipboard refuses', async () => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockRejectedValue(new Error('denied')) } });
    const { container } = inEnglish(<SecretOnce secret="https://example.test/feed.ics" copyLabel="Copy address" address onDone={vi.fn()} />);
    expect(container.querySelector('[data-feed-address]')).toHaveTextContent('https://example.test/feed.ics');
    fireEvent.click(screen.getByRole('button', { name: 'Copy address' }));
    await waitFor(() => expect(screen.queryByText('Copied.')).toBeNull());
  });
});

describe('Pager', () => {
  it('pages a list in time order Newer and Older, within the total', () => {
    const onOffset = vi.fn();
    inEnglish(<Pager inTime offset={20} limit={20} shown={20} total={45} onOffset={onOffset} />);
    expect(screen.getByText('21 to 40 of 45')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Newer' }));
    fireEvent.click(screen.getByRole('button', { name: 'Older' }));
    expect(onOffset.mock.calls).toEqual([[0], [40]]);
  });

  it('pages any other list Previous and Next, holding each at its end, in the list\'s own words where it has them', () => {
    inEnglish(<Pager offset={0} limit={20} shown={5} total={5} range="Newest 1 to 5 of 5" onOffset={vi.fn()} />);
    expect(screen.getByText('Newest 1 to 5 of 5')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
  });
});

describe('QueryState', () => {
  const query = (state: Partial<UseQueryResult<string[]>>) => state as UseQueryResult<string[]>;

  it('loads, fails with a retry, and hands over the data once it is there', () => {
    const refetch = vi.fn();
    const child = (items: string[]) => <p>{items.join(', ')}</p>;
    const { rerender } = inEnglish(<QueryState query={query({ isPending: true, isError: false })} errorTitle="The list could not be loaded">{child}</QueryState>);
    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true');
    const wrap = (node: ReactNode) => <LocaleProvider locale="en">{node}</LocaleProvider>;
    rerender(wrap(<QueryState query={query({ isPending: false, isError: true, refetch })} errorTitle="The list could not be loaded">{child}</QueryState>));
    expect(screen.getByRole('alert')).toHaveTextContent('The list could not be loaded');
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(refetch).toHaveBeenCalledTimes(1);
    rerender(wrap(<QueryState query={query({ isPending: false, isError: false, data: ['a', 'b'] })} errorTitle="The list could not be loaded">{child}</QueryState>));
    expect(screen.getByText('a, b')).toBeInTheDocument();
  });
});
