import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { renderWith } from '@/shared/testing/render';

import { DecideDialog } from './DecideDialog';

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
});
