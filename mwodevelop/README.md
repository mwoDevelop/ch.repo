# WatchNixtoons2 (mwoDevelop)

This subtree contains the reproducible source used to build
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

1. Let the central `mwoDevelop/kodi` discovery report the immutable upstream
   commit, release archive and digest.
2. Review the upstream license and update `upstream.json`.
3. Adjust only the declarative identity transforms or the ordered patch series
   when the new upstream tree requires it.
4. Bump the downstream version and verify byte-for-byte reconstruction:

   ```bash
   python3 tools/import_mwodevelop_watchnixtoons2.py --check
   python3 -m unittest discover -s mwodevelop/tests -v
   ```

5. Review `import-manifest.json`, then publish the exact fork commit through
   `mwoDevelop/kodi` testing first.
