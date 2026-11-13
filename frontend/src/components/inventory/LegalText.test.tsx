import { fireEvent, render, screen } from '@testing-library/react';
import { useState, type ReactNode } from 'react';
import { describe, expect, it } from 'vitest';

import type { LocalizedText, VersionDiff } from '@/features/library/types';
import { LocaleProvider } from '@/shared/i18n/LocaleProvider';

import { LegalText, RuleText } from './LegalText';

function renderIn(locale: 'en' | 'sv', node: ReactNode) {
  return render(<LocaleProvider locale={locale}>{node}</LocaleProvider>);
}

const svOriginal: LocalizedText = { text: 'Investeringsanalys får tas emot endast…', language: 'sv', isOriginal: true, isMachine: false };
const enMachine: LocalizedText = { text: 'Investment research may be received only…', language: 'en', isOriginal: false, isMachine: true };

/** RuleText as a screen holds it: the reader's choice in state, the shown text worked out from it. */
function Chosen({ texts, diff }: { texts: LocalizedText[]; diff?: VersionDiff }) {
  const [chosen, setChosen] = useState(texts[1]?.language ?? texts[0]?.language ?? '');
  const shown = texts.find((text) => text.language === chosen) as LocalizedText;
  return <RuleText texts={texts} shown={shown} onChoose={setChosen} diff={diff} />;
}

describe('LegalText', () => {
  it('sets the text beside a sand margin with a brass section sign and the reference', () => {
    const { container } = renderIn(
      'en',
      <LegalText reference="9 kap. 6 §">
        <p lang="sv">Investeringsanalys från tredje part får tas emot endast om den betalas med egna medel.</p>
      </LegalText>,
    );
    expect(screen.getByText(/^Investeringsanalys från tredje part/)).toHaveAttribute('lang', 'sv');
    const margin = container.querySelector('[data-legal-margin]');
    expect(margin).toHaveClass('bg-sand', 'text-brass');
    const sign = margin?.querySelector('[aria-hidden="true"]');
    expect(sign).toHaveTextContent('§');
    expect(sign).toHaveClass('font-mono');
    expect(margin).toHaveTextContent('9 kap. 6 §');
  });

  it('renders without a reference', () => {
    const { container } = renderIn('en', <LegalText>Text.</LegalText>);
    expect(container.querySelector('[data-legal-margin]')).toHaveTextContent(/^§$/);
  });
});

describe('RuleText', () => {
  it('labels a machine translation above the text, in the reader language and outside the text language', () => {
    renderIn('en', <Chosen texts={[svOriginal, enMachine]} />);
    const label = screen.getByText('Machine translation from Swedish. The original is authoritative.');
    expect(label).toHaveAttribute('data-provision-label');
    expect(label.closest('[lang]')).toBeNull();
    expect(screen.getByText(enMachine.text)).toHaveAttribute('lang', 'en');
  });

  it('names the original on its chip and above its text, and switches to it', () => {
    renderIn('sv', <Chosen texts={[svOriginal, enMachine]} />);
    expect(screen.getByText('Maskinöversättning från svenska. Originalet gäller.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'svenska, original' }));
    expect(document.querySelector('[data-provision-label]')).toHaveTextContent('svenska, original');
    expect(screen.getByText(svOriginal.text)).toHaveAttribute('lang', 'sv');
  });

  it('shows a comparison in place of the text, labelled for the language it was taken in', () => {
    const diff: VersionDiff = {
      fromVersion: 1,
      toVersion: 2,
      fromEffective: null,
      toEffective: null,
      fromConfirmation: null,
      toConfirmation: null,
      language: 'sv',
      isMachine: false,
      segments: [
        { op: 'equal', text: 'Investeringsanalys får tas emot.' },
        { op: 'insert', text: 'Institutet ska årligen bedöma analysen.' },
      ],
    };
    renderIn('en', <Chosen texts={[svOriginal, enMachine]} diff={diff} />);
    expect(document.querySelector('[data-provision-label]')).toHaveTextContent('Swedish, original');
    expect(document.querySelector('[data-provision-text]')).toHaveAttribute('lang', 'sv');
    expect(screen.getByText('Institutet ska årligen bedöma analysen.').tagName).toBe('INS');
  });
});
