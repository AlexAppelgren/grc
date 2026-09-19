import type { MessageKey } from '@/shared/i18n';

// Brand constants (playbook 7.2). The product name is a setting because the
// same build is white-labelled per tenant later; the backend owns the value
// (`PRODUCT_NAME`) and the frontend mirrors it at build time.
export const productName: string = process.env.NEXT_PUBLIC_PRODUCT_NAME ?? 'Compliance Watch';

// Empty until the owner supplies one (docs/TODO_FOR_alex.md). Screens hide the
// support link while it is empty rather than showing a placeholder address.
export const supportContact: string = process.env.NEXT_PUBLIC_SUPPORT_CONTACT ?? '';

// The accessible name of the phonetic wordmark, in the user's language.
export const logoNameKey: MessageKey = 'brand.logoName';

export const legalFooterKeys: readonly MessageKey[] = ['brand.legal', 'brand.privacy', 'brand.support'];
