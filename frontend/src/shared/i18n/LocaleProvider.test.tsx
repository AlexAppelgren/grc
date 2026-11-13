import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { LocaleProvider, useAdoptLocale, useLocale, useT } from './LocaleProvider';

function Probe() {
  const t = useT();
  const locale = useLocale();
  return (
    <p>
      {locale}:{t('nav.today')}
    </p>
  );
}

describe('LocaleProvider', () => {
  it('defaults to the configured locale without a provider', () => {
    render(<Probe />);
    expect(screen.getByText('en:Today')).toBeInTheDocument();
  });

  it('hands the chosen locale and its t to children', () => {
    render(
      <LocaleProvider locale="sv">
        <Probe />
      </LocaleProvider>,
    );
    expect(screen.getByText('sv:Idag')).toBeInTheDocument();
  });

  it("gives the signed-in person's language to what sits above the session, and gives it back when they leave", () => {
    function Adopt() {
      useAdoptLocale('sv');
      return null;
    }
    const tree = (signedIn: boolean) => (
      <LocaleProvider locale="en" adoptable>
        <Probe />
        {signedIn ? <Adopt /> : null}
      </LocaleProvider>
    );
    const { rerender } = render(tree(true));
    expect(screen.getByText('sv:Idag')).toBeInTheDocument();
    expect(document.documentElement.lang).toBe('sv');
    rerender(tree(false));
    expect(screen.getByText('en:Today')).toBeInTheDocument();
    expect(document.documentElement.lang).toBe('en');
  });

  it('leaves a provider that does not adopt as it is', () => {
    function Adopt() {
      useAdoptLocale('sv');
      return null;
    }
    render(
      <LocaleProvider locale="en">
        <Probe />
        <Adopt />
      </LocaleProvider>,
    );
    expect(screen.getByText('en:Today')).toBeInTheDocument();
  });
});
