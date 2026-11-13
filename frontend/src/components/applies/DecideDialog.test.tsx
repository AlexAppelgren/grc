import { QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';
import { renderWith } from '@/shared/testing/render';

import { DecideDialog, type Current } from './DecideDialog';

// The one dialog for every way in: it says what it covers, opens on Applies with the
// suggested reason, empties the reason for Does not apply, keeps the person's own words,
// and has one button that says what it does.

const SUGGESTION = 'Within the scope of its licence Tillstånd att driva fondverksamhet, which brings Funds into scope.';

function open(props: Partial<Parameters<typeof DecideDialog>[0]> = {}) {
  const onSubmit = vi.fn();
  const onClose = vi.fn();
  renderWith(<DecideDialog company="Example Fonder AB" covers="41 obligations in 6 regulations" count={41} suggestion={SUGGESTION} pending={false} onSubmit={onSubmit} onClose={onClose} {...props} />);
  return { onSubmit, onClose };
}

const reason = () => screen.getByLabelText<HTMLTextAreaElement>('Reason');
const hint = () => screen.queryByText('Suggested from the licence facts');

describe('DecideDialog', () => {
  it('asks about the company, says what it covers, and opens on Applies with the suggestion', () => {
    const { onSubmit } = open();
    const dialog = screen.getByRole('dialog', { name: 'Does it apply to Example Fonder AB?' });
    expect(dialog).toHaveAccessibleDescription('41 obligations in 6 regulations');
    expect(screen.getByRole('button', { name: 'Applies' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Does not apply' })).toHaveAttribute('aria-pressed', 'false');
    expect(reason().value).toBe(SUGGESTION);
    expect(hint()).toBeInTheDocument();
    expect(reason()).toHaveAccessibleDescription('Suggested from the licence facts');
    expect(screen.getByText('Each obligation gets its own entry in the audit log, with this reason.')).toBeInTheDocument();
    expect(screen.getByText('Anything a colleague decides in the meantime is left as it is.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Set 41 to Applies' }));
    expect(onSubmit).toHaveBeenCalledWith({ applicability: 'applies', reason: SUGGESTION });
  });

  it('drops the label as soon as the person edits the suggestion, and keeps their words through a change of answer', () => {
    const { onSubmit } = open({ count: 1 });
    fireEvent.change(reason(), { target: { value: `${SUGGESTION} The company buys research.` } });
    expect(hint()).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Does not apply' }));
    expect(reason().value).toBe(`${SUGGESTION} The company buys research.`);
    fireEvent.click(screen.getByRole('button', { name: 'Applies' }));
    expect(hint()).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Set 1 to Applies' }));
    expect(onSubmit).toHaveBeenCalledWith({ applicability: 'applies', reason: `${SUGGESTION} The company buys research.` });
  });

  it('empties the reason for Does not apply, with no label, and disables the button until the person gives one', () => {
    const { onSubmit } = open();
    fireEvent.click(screen.getByRole('button', { name: 'Does not apply' }));
    expect(reason().value).toBe('');
    expect(hint()).not.toBeInTheDocument();
    expect(reason()).toHaveAttribute('placeholder', 'e.g. The company holds no client money');
    const set = screen.getByRole('button', { name: 'Set 41 to Does not apply' });
    expect(set).toBeDisabled();
    fireEvent.change(reason(), { target: { value: '   ' } });
    expect(set).toBeDisabled();
    fireEvent.change(reason(), { target: { value: '  The company manages no funds of this kind. ' } });
    fireEvent.click(set);
    expect(onSubmit).toHaveBeenCalledWith({ applicability: 'not_applicable', reason: 'The company manages no funds of this kind.' });
  });

  it('restores the suggestion going back to Applies when the person typed nothing of their own', () => {
    open();
    fireEvent.click(screen.getByRole('button', { name: 'Does not apply' }));
    fireEvent.click(screen.getByRole('button', { name: 'Applies' }));
    expect(reason().value).toBe(SUGGESTION);
    expect(hint()).toBeInTheDocument();
    // Typed, then emptied: nothing of their own is left, so the suggestion comes back.
    fireEvent.click(screen.getByRole('button', { name: 'Does not apply' }));
    fireEvent.change(reason(), { target: { value: 'x' } });
    fireEvent.change(reason(), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Applies' }));
    expect(reason().value).toBe(SUGGESTION);
    expect(hint()).toBeInTheDocument();
  });

  it('waits while the start is sent, shows a refusal by its code, and closes on Cancel', () => {
    const { onClose } = open({ pending: true, error: { isAxiosError: true, response: { status: 404, data: { code: 'not_found', detail: 'x' } } }, codes: { not_found: 'No longer offered.' } });
    expect(screen.getByRole('button', { name: 'Set 41 to Applies' })).toBeDisabled();
    expect(screen.getByText('No longer offered.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onClose).toHaveBeenCalled();
  });

  it('speaks Swedish', () => {
    renderWith(<DecideDialog company="Example Fonder AB" covers="2 skyldigheter i FFFS 2013:9" count={2} suggestion="Förslag." pending={false} onSubmit={vi.fn()} onClose={vi.fn()} />, { locale: 'sv' });
    expect(screen.getByRole('dialog', { name: 'Gäller det Example Fonder AB?' })).toBeInTheDocument();
    expect(screen.getByText('Förslag utifrån tillståndsuppgifterna')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Gäller inte' }));
    expect(screen.getByRole('button', { name: 'Sätt 2 till Gäller inte' })).toBeDisabled();
  });

  it('offers no "Not assessed" to a run over many', () => {
    open();
    expect(screen.getAllByRole('button', { name: /^(Applies|Does not apply|Not assessed)$/ }).map((button) => button.textContent)).toEqual(['Applies', 'Does not apply']);
  });
});

describe('DecideDialog for one obligation', () => {
  function one(props: { company?: string | null; current?: Current | null; suggestion?: string } = {}) {
    const onSubmit = vi.fn();
    const view = renderWith(<DecideDialog company="Example Fonder AB" current={null} notAssessed suggestion={SUGGESTION} pending={false} onSubmit={onSubmit} onClose={vi.fn()} {...props} />);
    return { onSubmit, view };
  }

  /** The suggestion arriving after the dialog opened, as the obligation page's read answers. */
  function arrive(view: ReturnType<typeof one>['view']) {
    view.rerender(
      <QueryClientProvider client={view.queryClient}>
        <LocaleProvider locale="en">
          <DecideDialog company="Example Fonder AB" current={null} notAssessed suggestion={SUGGESTION} pending={false} onSubmit={vi.fn()} onClose={vi.fn()} />
        </LocaleProvider>
      </QueryClientProvider>,
    );
  }

  it('offers three answers for a row nobody answered, opens on Applies with the suggestion, and says what it is now', () => {
    const { onSubmit } = one();
    const dialog = screen.getByRole('dialog', { name: 'Does it apply to Example Fonder AB?' });
    expect(dialog).not.toHaveAccessibleDescription();
    expect(screen.getAllByRole('button', { name: /^(Applies|Does not apply|Not assessed)$/ }).map((button) => button.textContent)).toEqual(['Applies', 'Does not apply', 'Not assessed']);
    expect(screen.getByRole('button', { name: 'Applies' })).toHaveAttribute('aria-pressed', 'true');
    expect(reason().value).toBe(SUGGESTION);
    expect(hint()).toBeInTheDocument();
    expect(screen.getByText('Now: to decide')).toBeInTheDocument();
    // The lines about a run over many are not this dialog's.
    expect(screen.queryByText('Anything a colleague decides in the meantime is left as it is.')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Set to Applies' }));
    expect(onSubmit).toHaveBeenCalledWith({ applicability: 'applies', reason: SUGGESTION });
  });

  it('says each answer on its button with no count, empties the reason for the other two, and brings the suggestion back with Applies', () => {
    const { onSubmit } = one();
    fireEvent.click(screen.getByRole('button', { name: 'Does not apply' }));
    expect(reason().value).toBe('');
    expect(hint()).toBeNull();
    expect(screen.getByRole('button', { name: 'Set to Does not apply' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Not assessed' }));
    expect(reason().value).toBe('');
    fireEvent.click(screen.getByRole('button', { name: 'Applies' }));
    expect(reason().value).toBe(SUGGESTION);
    expect(hint()).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Not assessed' }));
    fireEvent.change(reason(), { target: { value: ' Waiting for the legal opinion. ' } });
    fireEvent.click(screen.getByRole('button', { name: 'Set to Not assessed' }));
    expect(onSubmit).toHaveBeenCalledWith({ applicability: 'under_assessment', reason: 'Waiting for the legal opinion.' });
  });

  it('opens an answered row on its answer and stored reason, with no suggestion, and never carries that reason to another answer', () => {
    const { onSubmit } = one({ current: { applicability: 'not_applicable', reason: 'The company holds no client money.' }, suggestion: '' });
    expect(screen.getByRole('button', { name: 'Does not apply' })).toHaveAttribute('aria-pressed', 'true');
    expect(reason().value).toBe('The company holds no client money.');
    expect(hint()).toBeNull();
    expect(screen.getByText('Now: Does not apply')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Applies' }));
    expect(reason().value).toBe('');
    expect(hint()).toBeNull();
    expect(screen.getByRole('button', { name: 'Set to Applies' })).toBeDisabled();
    // Back on the stored answer, the stored reason.
    fireEvent.click(screen.getByRole('button', { name: 'Does not apply' }));
    expect(reason().value).toBe('The company holds no client money.');
    fireEvent.click(screen.getByRole('button', { name: 'Applies' }));
    fireEvent.change(reason(), { target: { value: 'The company now holds client money.' } });
    fireEvent.click(screen.getByRole('button', { name: 'Set to Applies' }));
    expect(onSubmit).toHaveBeenCalledWith({ applicability: 'applies', reason: 'The company now holds client money.' });
  });

  it('empties a stored Applies reason for Does not apply, and puts it back with Applies', () => {
    one({ current: { applicability: 'applies', reason: 'We give advice and manage portfolios.' }, suggestion: '' });
    expect(reason()).not.toHaveAttribute('placeholder');
    fireEvent.click(screen.getByRole('button', { name: 'Does not apply' }));
    expect(reason().value).toBe('');
    expect(reason()).toHaveAttribute('placeholder', 'e.g. The company holds no client money');
    expect(screen.getByRole('button', { name: 'Set to Does not apply' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Applies' }));
    expect(reason().value).toBe('We give advice and manage portfolios.');
    expect(hint()).toBeNull();
  });

  it('opens a row stored as Not assessed on Applies with the suggestion, and the stored reason back on Not assessed', () => {
    one({ current: { applicability: 'under_assessment', reason: 'Waiting for the legal opinion.' } });
    expect(screen.getByRole('button', { name: 'Applies' })).toHaveAttribute('aria-pressed', 'true');
    expect(reason().value).toBe(SUGGESTION);
    expect(hint()).toBeInTheDocument();
    expect(screen.getByText('Now: Not assessed')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Not assessed' }));
    expect(reason().value).toBe('Waiting for the legal opinion.');
    expect(hint()).toBeNull();
  });

  it('asks about us for the obligation as a whole', () => {
    one({ company: null, suggestion: '' });
    expect(screen.getByRole('dialog', { name: 'Does it apply to us?' })).toBeInTheDocument();
    expect(reason().value).toBe('');
    expect(hint()).toBeNull();
    // An empty field beside Applies shows no example reason for Does not apply.
    expect(reason()).not.toHaveAttribute('placeholder');
  });

  it('puts in a suggestion that arrives late while the field holds nothing of the person\'s own, and never over what they typed', () => {
    const { view } = one({ suggestion: '' });
    expect(reason().value).toBe('');
    expect(hint()).toBeNull();
    arrive(view);
    expect(reason().value).toBe(SUGGESTION);
    expect(hint()).toBeInTheDocument();
  });

  it('leaves what the person typed alone when the suggestion arrives after it', () => {
    const { view } = one({ suggestion: '' });
    fireEvent.change(reason(), { target: { value: 'The fund company buys research.' } });
    arrive(view);
    expect(reason().value).toBe('The fund company buys research.');
    expect(hint()).toBeNull();
  });

  it('speaks Swedish', () => {
    renderWith(<DecideDialog company={null} current={{ applicability: 'applies', reason: 'Vi ger råd.' }} notAssessed suggestion="" pending={false} onSubmit={vi.fn()} onClose={vi.fn()} />, { locale: 'sv' });
    expect(screen.getByRole('dialog', { name: 'Gäller den oss?' })).toBeInTheDocument();
    expect(screen.getByText('Just nu: Gäller')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Sätt till Gäller' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: 'Inte bedömd' }));
    expect(screen.getByRole('button', { name: 'Sätt till Inte bedömd' })).toBeDisabled();
  });
});
