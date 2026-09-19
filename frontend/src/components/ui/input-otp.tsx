'use client';

import { OTPInput, REGEXP_ONLY_DIGITS, type SlotProps } from 'input-otp';

import { cn } from '@/shared/utils/cn';

// The emailed code (design/screens/auth-code.html, ID-02): one real input
// behind six visual slots (input-otp, MIT). A single input is what keeps
// paste, the numeric keyboard, `autocomplete="one-time-code"` autofill and a
// screen reader working; six separate inputs break each of them. The label
// comes from the surrounding Field through `id`.

export const OTP_LENGTH = 6;

/** A code copied from the email may carry a space or a line break ("123 456"). */
export function digitsOnly(pasted: string): string {
  return pasted.replace(/\D/g, '');
}

function Slot({ char, isActive, hasFakeCaret, invalid }: SlotProps & { invalid: boolean }) {
  return (
    <div
      data-slot="otp-slot"
      data-active={isActive || undefined}
      className={cn(
        'relative flex h-12 w-11 items-center justify-center rounded-control border bg-surface font-mono text-[1.3rem] text-fg',
        invalid ? 'border-negative' : 'border-line-strong',
        isActive && 'outline-2 outline-offset-2 outline-focus outline-solid',
      )}
    >
      {char}
      {hasFakeCaret ? <span aria-hidden="true" className="h-5 w-px bg-fg motion-safe:animate-pulse" /> : null}
    </div>
  );
}

export function InputOtp({
  id,
  value,
  onChange,
  onComplete,
  invalid = false,
  disabled,
  describedBy,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  /** Called with the full code once every slot is filled, typed or pasted. */
  onComplete: (code: string) => void;
  invalid?: boolean;
  disabled?: boolean;
  describedBy?: string;
}) {
  return (
    <OTPInput
      id={id}
      name={id}
      maxLength={OTP_LENGTH}
      pattern={REGEXP_ONLY_DIGITS}
      pasteTransformer={digitsOnly}
      inputMode="numeric"
      autoComplete="one-time-code"
      value={value}
      onChange={onChange}
      onComplete={onComplete}
      disabled={disabled}
      aria-invalid={invalid || undefined}
      aria-describedby={describedBy}
      containerClassName="flex items-center gap-2 has-disabled:opacity-45"
      render={({ slots }) => (
        <div className="flex gap-2">
          {slots.map((slot, index) => (
            // The slots are positions, fixed for the life of the input.
            <Slot key={index} {...slot} invalid={invalid} />
          ))}
        </div>
      )}
    />
  );
}
