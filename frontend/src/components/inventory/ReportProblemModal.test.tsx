import { fireEvent, render, screen } from '@testing-library/react';
import { AxiosError } from 'axios';
import { describe, expect, it, vi } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';

import { ReportProblemModal, type ReportMutation } from './ReportProblemModal';

// "This looks wrong" (INV-06, INV-S7): the reader's own words, sent once, and
// acknowledged. The form takes the description alone; there is no "Where"
// select until the field becomes a vocabulary.

function mutation(over: Partial<ReportMutation> = {}): ReportMutation {
  return { mutate: vi.fn(), isPending: false, isError: false, error: null, data: undefined, reset: vi.fn(), ...over };
}

function renderModal(report: ReportMutation, onOpenChange = vi.fn()) {
  render(
    <LocaleProvider locale="en">
      <ReportProblemModal open onOpenChange={onOpenChange} context={{ versionNumber: 2, language: 'en' }} report={report} />
    </LocaleProvider>,
  );
  return onOpenChange;
}

describe('ReportProblemModal', () => {
  it('refuses to send nothing, and sends the words with what was on screen', () => {
    const report = mutation();
    renderModal(report);
    const send = screen.getByRole('button', { name: 'Send report' });
    expect(send).toBeDisabled();
    // Whitespace is not a description.
    fireEvent.change(screen.getByLabelText('What you see'), { target: { value: '   ' } });
    expect(send).toBeDisabled();

    fireEvent.change(screen.getByLabelText('What you see'), { target: { value: '  The English says annually.  ' } });
    fireEvent.click(send);
    expect(report.mutate).toHaveBeenCalledWith({ description: 'The English says annually.', versionNumber: 2, language: 'en' });
  });

  it('says the report stays inside the reader\'s own organisation', () => {
    renderModal(mutation());
    expect(screen.getByText('Colleagues in your organisation read this and take it up. It reaches nobody outside your organisation.')).toBeInTheDocument();
  });

  it('acknowledges a report that was filed, and clears the form on the way out', () => {
    const report = mutation({ data: { id: 'rep-1', status: 'open', createdAt: '2026-09-21T09:00:00Z' } });
    const onOpenChange = renderModal(report);
    expect(screen.getByText('Report sent. Thank you.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Send report' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(report.reset).toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('renders the server\'s refusal where the reader sent it', () => {
    const error = new AxiosError('bad', '422', undefined, undefined, {
      status: 422,
      data: { detail: 'The description is too long.', code: 'validation_error' },
      statusText: '422',
      headers: {},
      config: { headers: undefined as never },
    });
    renderModal(mutation({ isError: true, error }));
    expect(screen.getByRole('alert')).toHaveTextContent('The description is too long.');
  });

  it('closes without sending when the reader cancels', () => {
    const report = mutation();
    const onOpenChange = renderModal(report);
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(report.mutate).not.toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
