import { expect, test } from './support/api-guard';

// D-04 spike: a Green Core React component renders AND hydrates under
// `next start`. Clicking the button must change React state; un-hydrated
// HTML would leave the count at zero.

test.describe('green core spike', () => {
  test('GdsButton renders and hydrates under next start', async ({ page }) => {
    await page.goto('/dev/green-spike');
    const button = page.getByRole('button', { name: 'Count clicks' });
    await expect(button).toBeVisible();
    await expect(page.getByTestId('spike-count')).toHaveText('Not clicked yet');
    await button.click();
    await expect(page.getByTestId('spike-count')).toHaveText('Clicked 1 time');
    await button.click();
    await expect(page.getByTestId('spike-count')).toHaveText('Clicked 2 times');
    // The custom element is defined, so it is a real web component and not a fallback.
    const defined = await page.evaluate(() => {
      const el = document.querySelector('[data-testid="spike-count"]')?.parentElement?.querySelector('*[rank]');
      return el !== null && el !== undefined && customElements.get(el.tagName.toLowerCase()) !== undefined;
    });
    expect(defined).toBe(true);
  });
});
