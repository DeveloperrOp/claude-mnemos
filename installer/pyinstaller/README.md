# PyInstaller bundle

Build the bundle locally on Windows:

```
python -m pip install pyinstaller==6.11.0
python -m PyInstaller installer/pyinstaller/mnemos.spec --noconfirm
```

Output: `dist/claude-mnemos/claude-mnemos.exe` plus supporting DLLs / assets in
`dist/claude-mnemos/_internal/`.

Smoke test:

```
./dist/claude-mnemos/claude-mnemos.exe doctor
```

If a runtime ImportError surfaces, add the missing module to `hiddenimports` in
`mnemos.spec` and rebuild.

Mac and Linux bundles are produced by CI (`.github/workflows/release.yml`)
on the `macos-latest` and `ubuntu-latest` runners — they are not built locally.
