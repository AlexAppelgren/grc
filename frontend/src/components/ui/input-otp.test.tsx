import { act, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { InputOtp, OTP_LENGTH } from './input-otp';

// One real input behind six slots: typing, pasting a whole code, backspace,
// and the submit that fires once every slot is filled.

function Harness({ onSubmit, invalid = false, disabled = false }: { onSubmit: (code: string) => void; invalid?: boolean; disabled?: boolean }) {
  const [value, setValue] = useState('');
  return (
    <form>
      <label htmlFor="code">Code</label>
      <InputOtp id="code" value={value} onChange={setValue} onComplete={onSubmit} invalid={invalid} disabled={disabled} describedBy="code-hint" />
    </form>
  );
}

function input(): HTMLInputElement {
  return screen.getByLabelText('Code');
}

function filled(container: HTMLElement): string {
  return [...container.querySelectorAll('[data-slot="otp-slot"]')].map((slot) => slot.textContent).join('');
}

describe('InputOtp', () => {
  it('is one labelled numeric input with one-time-code autofill and six slots', () => {
    const { container } = render(<Harness onSubmit={vi.fn()} />);
    const field = input();
    expect(field.tagName).toBe('INPUT');
    expect(field).toHaveAttribute('inputmode', 'numeric');
    expect(field).toHaveAttribute('autocomplete', 'one-time-code');
    expect(field).toHaveAttribute('maxlength', String(OTP_LENGTH));
    expect(field).toHaveAttribute('aria-describedby', 'code-hint');
    expect(field).not.toHaveAttribute('aria-invalid');
    expect(container.querySelectorAll('input')).toHaveLength(1);
    expect(container.querySelectorAll('[data-slot="otp-slot"]')).toHaveLength(OTP_LENGTH);
  });

  it('fills the slots as digits are typed and submits once the sixth arrives', () => {
    const onSubmit = vi.fn();
    const { container } = render(<Harness onSubmit={onSubmit} />);
    for (const code of ['1', '12', '123', '1234', '12345']) fireEvent.change(input(), { target: { value: code } });
    expect(filled(container)).toBe('12345');
    expect(onSubmit).not.toHaveBeenCalled();
    fireEvent.change(input(), { target: { value: '123456' } });
    expect(filled(container)).toBe('123456');
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith('123456');
  });

  it('refuses anything but digits', () => {
    const { container } = render(<Harness onSubmit={vi.fn()} />);
    fireEvent.change(input(), { target: { value: '12a' } });
    expect(filled(container)).toBe('');
  });

  it.each(['654321', '654 321\n'])('fills every slot from one paste of %j and submits', (pasted) => {
    const onSubmit = vi.fn();
    const { container } = render(<Harness onSubmit={onSubmit} />);
    act(() => input().focus());
    fireEvent.paste(input(), { clipboardData: { getData: () => pasted } });
    expect(filled(container)).toBe('654321');
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith('654321');
  });

  it('removes the last digit on backspace', () => {
    const { container } = render(<Harness onSubmit={vi.fn()} />);
    fireEvent.change(input(), { target: { value: '123' } });
    act(() => input().focus());
    fireEvent.keyDown(input(), { key: 'Backspace' });
    fireEvent.change(input(), { target: { value: '12' } });
    expect(filled(container)).toBe('12');
  });

  it('marks the active slot for the focus ring and shows the invalid and disabled states', () => {
    const { container, rerender } = render(<Harness onSubmit={vi.fn()} invalid />);
    expect(input()).toHaveAttribute('aria-invalid', 'true');
    act(() => input().focus());
    fireEvent.focus(input());
    expect(container.querySelector('[data-slot="otp-slot"][data-active]')).not.toBeNull();
    rerender(<Harness onSubmit={vi.fn()} disabled />);
    expect(input()).toBeDisabled();
  });
});
