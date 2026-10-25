# Open Canvas login branding

The deployed Cognito managed login uses the same palette and three-bar wordmark
as the writing workspace. The existing Essentials plan supports this branding;
the user-pool tier and authentication policies were not changed.

## Assets and settings

- `wordmark.svg` is the editable logo source; `wordmark.png` is its transparent
  rendered asset for Cognito.
- `favicon.svg` reuses the same mark.
- `settings.json` records the applied theme.
- `apply_branding.py` maps the current Cognito settings to the workspace palette
  and uploads the assets for one app client.

The managed-login domain uses version `2`. The ALB authorization request includes
`lang=ko`, so login and recovery screens use Korean. The existing legacy client
also has a default managed-login branding record, preserving its ability to
authenticate if the prior application is restored.

Reapply a theme to a configured client:

```bash
apps/backend/.venv/bin/python deploy/cognito/apply_branding.py \
  --user-pool-id USER_POOL_ID \
  --client-id APP_CLIENT_ID \
  --region ap-northeast-2
```

`deploy/prepare_template.py` preserves the existing authorization language
parameters and domain settings on subsequent application deployments.

## Visual verification

The live login page was checked at 1440×1000 and 390×844. Both showed Korean
labels, the loaded custom logo, green primary buttons (`#345c44`) with 6px
corners, and no horizontal overflow or browser errors.

Branding does not reveal or change Cognito passwords. User provisioning and
password changes are separate administrative operations.
