# Linux AppImage

CI builds this on `ubuntu-latest`. Local builds require Linux x86_64.

## Local prerequisites

```
sudo apt-get install -y libfuse2 imagemagick
```

linuxdeploy is downloaded automatically by the build script if not present.

## Build

```
bash installer/linux/build-appimage.sh
```

Output: `installer/linux/dist/claude-mnemos-x86_64.AppImage`.

Make the AppImage executable (`chmod +x`) and run it directly. To integrate
with the desktop environment:

```
./claude-mnemos-x86_64.AppImage --integrate
```

(linuxdeploy adds a `.desktop` entry to `~/.local/share/applications/`.)

## Runtime requirements

The AppImage requires `webkit2gtk-4.0` to render the launcher window. On
Ubuntu/Debian:

    sudo apt install libwebkit2gtk-4.0-37

On Fedora:

    sudo dnf install webkit2gtk4.0
