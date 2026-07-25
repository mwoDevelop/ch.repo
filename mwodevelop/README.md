# WatchNixtoons2 (mwoDevelop)

This subtree contains the source used to build
`plugin.video.watchnixtoons2.mwodevelop`. It is intentionally separate from
the upstream repository catalogue so upstream updates can be merged without
mixing downstream changes into the original packages.

## Upstream

- Repository: `christianhaitian/ch.repo`
- Package: `plugin.video.watchnixtoons2.kodi19`
- Imported release: `0.25`
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

1. Merge or fetch the latest upstream `master`.
2. Select a new upstream WatchNixtoons2 release and verify its archive digest.
3. Update the runtime files under
   `plugin.video.watchnixtoons2.mwodevelop`, preserving the downstream changes
   listed above.
4. Update `upstream.json`, bump the downstream version and run:

   ```bash
   python3 -m unittest discover -s mwodevelop/tests -v
   ```

5. Publish the exact fork commit through `mwoDevelop/kodi` testing first.
