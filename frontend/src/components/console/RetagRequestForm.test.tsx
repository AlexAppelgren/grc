import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { installAdapter, queryWrapper, resetApiForTests, type Sent } from '@/shared/testing/api-adapter';
import { tokenStore } from '@/shared/utils/api-client';

import { RetagRequestForm } from './RetagRequestForm';

// "Ask for a re-tag" (design/screens/console-queue-batch.html, section 8; AGT-05): the
// term is matched with the picker's own near match against the live taxonomy, the
// request is filed as a job, and the form follows it until the batch appears.

const REQUESTS = '/api/v1/console/research-requests';

const terms = [
  { id: 't-1', key: 'client_money', label: 'Client money', dimension: 'service_type', active: true, mirrored: false },
  { id: 't-2', key: 'se', label: 'Sweden', dimension: 'market', active: true, mirrored: true },
];

const request = { id: 'q-1', kind: 'retag', tenantAgentId: null, topic: '', sourceId: null, url: null, status: 'queued', requestedBy: { id: 'u10', name: 'Ida Holm' }, createdAt: '2026-09-25T08:00:00Z', completedAt: null, batchProposalId: null };

function serve(status: (count: number) => Record<string, unknown>): Sent[] {
  let reads = 0;
  return installAdapter((sent) => {
    if (sent.path === '/api/v1/taxonomy/terms') return { status: 200, data: { items: terms, total: terms.length } };
    if (sent.path === REQUESTS && sent.method === 'post') return { status: 202, data: request };
    if (sent.path === `${REQUESTS}/q-1`) {
      reads += 1;
      return { status: 200, data: { ...request, ...status(reads) } };
    }
    return { status: 403, data: { code: 'forbidden', detail: 'Not for this test.' } };
  });
}

function renderForm(onClose = vi.fn()): void {
  const { wrapper: Query } = queryWrapper();
  render(
    <Query>
      <LocaleProvider locale="en">
        <RetagRequestForm onClose={onClose} />
      </LocaleProvider>
    </Query>,
  );
}

async function typeTerm(text: string): Promise<void> {
  await waitFor(() => expect(document.querySelector('[data-retag-form]')).not.toBeNull());
  fireEvent.change(screen.getByLabelText('Term'), { target: { value: text } });
}

describe('asking for a re-tag', () => {
  beforeEach(() => {
    resetApiForTests();
    tokenStore.set('tok');
  });

  it('offers the term the taxonomy holds for a near miss, and uses it on a click', async () => {
    serve(() => ({}));
    renderForm();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Ask for the re-tag' })).toBeDisabled());
    await typeTerm('client monies');
    expect(await screen.findByText('Did you mean Client money?')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Use Client money' }));
    expect(screen.getByLabelText('Term')).toHaveValue('Client money');
    expect(screen.queryByText('Did you mean Client money?')).toBeNull();
  });

  it('never offers a term of the mirrored jurisdiction dimension', async () => {
    serve(() => ({}));
    renderForm();
    await typeTerm('Sweden');
    expect(await screen.findByText('No term is called that.')).toBeInTheDocument();
  });

  it('files the request as one topic naming the term by key, and follows it to the batch', async () => {
    const sent = serve((count) => (count === 1 ? { status: 'running' } : { status: 'done', batchProposalId: 'b-1' }));
    renderForm();
    await typeTerm('client money');
    fireEvent.change(screen.getByLabelText('Which obligations'), { target: { value: 'Obligations under PSD2 that hold client funds' } });
    fireEvent.change(screen.getByLabelText('Why'), { target: { value: 'New guidance' } });
    fireEvent.click(screen.getByRole('button', { name: 'Ask for the re-tag' }));

    expect(await screen.findByText('Sent. The batch is being prepared.')).toBeInTheDocument();
    const link = await screen.findByRole('link', { name: 'Open the batch' }, { timeout: 6000 });
    expect(link).toHaveAttribute('href', '/console/queue/batches/b-1');
    expect(sent.filter((s) => s.method === 'post').map((s) => s.body)).toEqual([
      { topic: 'Add the term Client money (service_type:client_money) to: Obligations under PSD2 that hold client funds Why: New guidance' },
    ]);
    expect(screen.getByRole('button', { name: 'Ask for the re-tag' })).toBeDisabled();
  });

  it('says so when the request ends without a batch', async () => {
    serve(() => ({ status: 'failed' }));
    renderForm();
    await typeTerm('Client money');
    fireEvent.change(screen.getByLabelText('Change'), { target: { value: 'remove' } });
    fireEvent.change(screen.getByLabelText('Which obligations'), { target: { value: 'Custody duties' } });
    fireEvent.click(screen.getByRole('button', { name: 'Ask for the re-tag' }));
    expect(await screen.findByText('The request ended without a batch.')).toBeInTheDocument();
  });

  it('closes on Cancel', async () => {
    serve(() => ({}));
    const onClose = vi.fn();
    renderForm(onClose);
    await waitFor(() => expect(document.querySelector('[data-retag-form]')).not.toBeNull());
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onClose).toHaveBeenCalledOnce();
  });
});
