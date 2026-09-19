# Third-party notices

This product includes software developed by third parties. The notices below
are required by the licences of the packages named; the full dependency tree
and its licences are checked in CI by `scripts/check_licences.py` (playbook 9,
"Dependency licences").

## SEB Green Design System (Apache License 2.0)

The user interface is built on the SEB Green Design System. The following
packages are licensed under the Apache License, Version 2.0:

- `@sebgroup/green-tokens` — design tokens (colour, spacing, typography)
- `@sebgroup/green-core` — web components

Copyright Skandinaviska Enskilda Banken AB (publ). Licensed under the Apache
License, Version 2.0 (the "License"); you may not use these files except in
compliance with the License. You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
License for the specific language governing permissions and limitations under
the License.

Any `NOTICE` file shipped inside a `@sebgroup/*` package applies in addition
to this notice. Modifications: the design tokens are compiled into
`src/styles/tokens.generated.css` by `scripts/build-tokens.mjs`; the token
values are not altered. Brand overrides live in `src/styles/brand.css`.

## Passkey provider names (community list, no licence published)

A new passkey is named after its provider ("Windows Hello", "Google Password
Manager", "1Password") from the community-sourced list at
https://github.com/passkeydeveloper/passkey-authenticator-aaguids
(`aaguid.json`, fetched 2026-09-19). The names only, not the icons, are
vendored in `backend/apps/identity/data/passkey_aaguid_names.tsv`, whose
header records the commit. The repository publishes no licence, so no notice
is required; this credit is a courtesy, and the list is used only for the one
purpose its README names: naming passkeys in a person's own passkey list.
Provider and product names belong to their owners.

## Adding a package that needs attribution

When a new `@sebgroup/*` package is installed, add it to the list above; the
CI licence gate fails until it is listed. Other Apache-2.0 packages with a
`NOTICE` file are listed here as well when they are shipped to end users.
