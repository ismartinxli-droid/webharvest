# Build & Distribution

WebHarvest uses a pure Swift Package Manager build, so you don't need the full Xcode IDE to compile. The pipeline is:

```
Swift source ──swift build──▶ Mach-O binary
                                  │
                                  ▼
                         ┌────────────────┐
                         │  WebHarvest.app │  ← assembled bundle
                         │  + Info.plist   │
                         │  + Python PBS   │  ← embedded runtime
                         │  + webharvest   │
                         └────────────────┘
                                  │
                                  ▼
                            create-dmg
                                  │
                                  ▼
                      WebHarvest-x.y.z-arm64.dmg
```

## Three ways to build

### 1. GitHub Actions (zero local setup) — recommended

You don't need any Mac toolchain installed. Push to GitHub and CI does the work.

```bash
# one-time setup
git init
git add . && git commit -m "initial"
git remote add origin git@github.com:YOU/webharvest.git
git push -u origin main

# trigger a release build
git tag v0.1.0
git push origin v0.1.0

# → go to github.com/YOU/webharvest/actions
# → download the "WebHarvest-arm64-dmg" artifact
# → or get the auto-created GitHub Release (draft)
```

The CI workflow is in `.github/workflows/release.yml`. It:
1. Runs Python smoke tests
2. `swift build -c release --arch arm64`
3. Assembles the .app bundle
4. Embeds Python 3.11 (python-build-standalone)
5. Strips quarantine metadata (`xattr -cr`) for zero-friction install
6. Creates the .dmg
7. Uploads as artifact + creates a GitHub Release (on tag)

### 2. Local build with SwiftPM only (~700 MB CLT)

```bash
# one-time
xcode-select --install                  # ~700 MB, no full Xcode
brew install create-dmg                 # for DMG packaging

# build
./build/release.sh

# → dist/WebHarvest-0.1.0-arm64.dmg
```

### 3. Local dev loop

```bash
./build/dev.sh
# creates venv, installs deps, runs tests, swift build, launches app
```

## Verifying a built .dmg

```bash
hdiutil attach dist/WebHarvest-0.1.0-arm64.dmg
open /Volumes/WebHarvest/WebHarvest.app
# click through Gatekeeper: right-click → Open (ad-hoc signed)
hdiutil detach /Volumes/WebHarvest
```

## Code signing (not needed for self-use)

The build scripts use **`xattr -cr` only** — no codesign, no notarization, no Apple Developer account. This is enough for self-use on your own Mac.

After install:
- Just drag the .app from the .dmg to /Applications
- **No Gatekeeper warning, no "right-click → Open" needed**
- App launches immediately on first double-click

### When you actually need real signing

Skip until you decide to distribute. If/when that day comes, you'll need:
- Apple Developer Program membership ($99/year)
- Developer ID Application certificate
- Notarization via `xcrun notarytool`

For v0.1 self-use, none of this is required.

### Migrating from `xattr -cr` to proper signing

In `build/release.sh` and `.github/workflows/release.yml`, replace the `xattr -cr` line with:

```bash
codesign --force --deep --sign "Developer ID Application: Your Name (TEAMID)" \
    dist/WebHarvest.app
codesign --verify --verbose=2 dist/WebHarvest.app
```

## What goes wrong and how to fix it

| Symptom | Cause | Fix |
|---|---|---|
| `xcode-select: error` | CLT not installed | `xcode-select --install` |
| `swift: command not found` | CLT not installed | `xcode-select --install` |
| `architecture mismatch` warning | Building on Intel Mac | This app is arm64-only — use an Apple Silicon Mac |
| `Gatekeeper: can't be opened` | Ad-hoc sign + first launch | Right-click → Open (only first time) |
| `xattr: command not found` | macOS < 10.8 | Unlikely on Apple Silicon Macs; update OS |
| `python3 not found in bundle` | PBS download failed | Re-run; check internet; PBS tag in script may be stale (see [python-build-standalone releases](https://github.com/astral-sh/python-build-standalone/releases)) |
| App launches but Python errors | `webharvest` not in `site-packages` | Re-run `build/release.sh`; or check `dist/WebHarvest.app/Contents/Resources/python/site-packages/webharvest/` exists |
| Gatekeeper warning on launch | `xattr -cr` didn't run | Run manually: `xattr -cr /Applications/WebHarvest.app` |
