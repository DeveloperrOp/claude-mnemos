# macOS build

CI builds this on `macos-latest`. Local builds require macOS.

## Local prerequisites

```
brew install create-dmg
pip install py2app==0.28.6
```

## Build

```
bash installer/macos/build-dmg.sh
```

Output: `installer/macos/dist/claude-mnemos.dmg`.

The bundle is unsigned. First-run users will see a Gatekeeper warning;
right-click → Open to accept it once. We will sign the app with a
Developer ID Application certificate when budget allows.
