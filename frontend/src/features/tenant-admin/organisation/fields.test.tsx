import { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { LocaleProvider } from '@/shared/i18n/LocaleProvider';

import { DialogForm } from './fields';

// The dialog every organisation form sits in (TEN-02): it submits without the
// browser's own validation, closes on Cancel and on Escape alike, and shows a
// stale write in the screen's own sentence when no field took the problem.

function stale(): AxiosError {
  const config = { headers: {} } as InternalAxiosRequestConfig;
  const data = { code: 'stale_write', detail: 'Changed.' };
  return new AxiosError('refused', '409', config, undefined, { data, status: 409, statusText: '', headers: {}, config });
}

function renderDialog(props: { error?: unknown; formLevel?: boolean; pending?: boolean } = {}) {
  const onSubmit = vi.fn();
  const onClose = vi.fn();
  render(
    <LocaleProvider locale="en">
      <DialogForm title="Edit entity" error={props.error ?? null} formLevel={props.formLevel ?? false} pending={props.pending ?? false} onSubmit={onSubmit} onClose={onClose}>
        <input aria-label="Name" defaultValue="Example Bank AB" />
      </DialogForm>
    </LocaleProvider>,
  );
  return { onSubmit, onClose };
}

describe('DialogForm', () => {
  it('saves through its own submit and shows no alert while nothing was refused', () => {
    const { onSubmit, onClose } = renderDialog();
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('closes on Escape as it does on Cancel, without saving', () => {
    const { onSubmit, onClose } = renderDialog();
    fireEvent.keyDown(screen.getByRole('dialog', { name: 'Edit entity' }), { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onClose).toHaveBeenCalledTimes(2);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('reads a stale write in the screen\'s own sentence, and holds Save while the write is pending', () => {
    renderDialog({ error: stale(), formLevel: true, pending: true });
    expect(screen.getByRole('alert')).toHaveTextContent('Someone changed this while you were editing. Close it and open it again to see their change.');
    expect(screen.getByRole('button', { name: 'Save' })).toBeDisabled();
  });
});
