# WatchNixtoons2 (mwoDevelop)

This subtree contains the reproducible source used to build
`plugin.video.watchnixtoons2.mwodevelop`. It is intentionally separate from
the upstream repository catalogue so upstream updates can be merged without
mixing downstream changes into the original packages.

## Upstream

- Repository: `christianhaitian/ch.repo`
- Package: `plugin.video.watchnixtoons2.kodi19`
- Imported release: `0.26`
- Import metadata and the exact archive digest: `upstream.json`

The runtime source was extracted from the upstream release archive. Original
authors and contributors remain credited in `addon.xml`; the package is
distributed under GPL-3.0-only.

## Downstream changes

- independent add-on ID and profile:
  `plugin.video.watchnixtoons2.mwodevelop`;
- settings actions target the independent add-on ID instead of the legacy
  `plugin.video.watchnixtoons2` ID;
- the fallback JWPlayer resolver uses Python 3 text consistently;
- signed cookie values containing `=` are parsed safely;
- InputStream Adaptive is optional and HLS falls back to Kodi's native player
  when a compatible platform binary is unavailable;
- explicit Kodi 19+ Python dependency;
- source and license metadata;
- package checks under `tests/`.

## Updating

The scheduled `propose WatchNixtoons2 upstream update` workflow discovers the
version declared by the current upstream `addon.xml` (it never selects an older
ZIP by filename), verifies the matching archive and prepares a content-addressed
candidate in a job without write permissions. A separate writer job can copy
only the allowlisted `mwodevelop/` files and opens or updates a PR. It never
merges the PR or publishes a Kodi repository release.

For a local dry run:

```bash
python3 tools/prepare_mwodevelop_watchnixtoons2_update.py discover \
  --output discovery.json
python3 tools/prepare_mwodevelop_watchnixtoons2_update.py prepare \
  --discovery discovery.json --output candidate
python3 tools/prepare_mwodevelop_watchnixtoons2_update.py verify \
  --bundle candidate
```

After review, merge the component PR and publish the exact fork commit through
`mwoDevelop/kodi` testing first. Stable promotion remains a separate manual
decision.
