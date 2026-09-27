import { TokensScreen } from '@/features/personal-tokens/TokensScreen';

// /me/tokens (design/screens/me-tokens.html; ACC-03). Every member's own page:
// without tokens.create it lists and revokes what they hold and says why
// there is no Create button, so it has no denied state.
export default function TokensPage() {
  return <TokensScreen />;
}
