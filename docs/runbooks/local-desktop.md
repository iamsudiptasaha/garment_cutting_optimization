# Local development and LAN desktop hosting

## Developer setup
In an activated Python 3.13 virtual environment, install the GUI and
existing input, geometry, processor and output dependencies:

~~~bash
python -m pip install -e ".[dev,geometry,solver,output,app]"
python -m garment_nesting.app dev
~~~

Open http://127.0.0.1:8080 in your browser. The NiceGUI development server
restarts on Python code changes. Stop with Ctrl-C. After merging updates:

~~~bash
git pull origin main
python -m garment_nesting.app dev
~~~

Re-run the pip install only if dependencies change.
To test the desktop Start/Stop launcher from source:

~~~bash
python -m garment_nesting.app
~~~

## One-click packaged application
The Desktop Builds workflow runs on PRs and on every main push. It produces
Windows x64, macOS Apple Silicon and macOS Intel ZIP artifacts, retained
for 30 days. Open the workflow run attached to the commit to download.

1. Extract the ZIP completely.
2. Windows: open NestingOptimizer/NestingOptimizer.exe.
   macOS: open NestingOptimizer.app.
3. Press **Start Server**; use **Open Browser** on the hosting machine.
4. Another device on the trusted LAN opens the displayed URL.
5. Press Stop or close the desktop launcher to stop sharing.

The host must stay powered on. The service uses port 8080; its host OS
firewall may require a one-time permission. A changing local IP changes the
shared URL. On Macs with no automatically discoverable LAN address the
launcher shows localhost only; LAN routing configuration needs attention.

Windows builds and macOS builds are presently unsigned, and macOS bundles
are not notarized. The OS may warn on first opening. Code signing, installer
distribution, login, and access control are later production-hardening work.

## Diagnostics

- Windows log: %LOCALAPPDATA%/NestingOptimizer/server.log
- macOS log: ~/Library/Application Support/NestingOptimizer/server.log

## Scope of the current UI foundation

The browser provides multi-file SVG intake and geometry inspection by
calling the existing input and geometry layers, without changing the SVG.
This is an early workspace, not the completed nesting experiment GUI:
multipliers, included-piece switches, per-piece rotations, plugin
algorithms, comparison and selected-result export are still pending.
The uploads are transient, and the quantity/rotation columns are currently
non-editable placeholders. Do not assume inventory equals saved job state.

## Security

The initial LAN host uses plain HTTP and has **no authentication**.
Run on a trusted isolated network, never internet port-forward port 8080.
Add operator authorization and persistent job storage before deploying
to general staff. The bundle can execute the PackingSolver and use the
resvg_py renderer without separately installing the Cairo system library.
CI executable smoke tests do not replace real machine/phone acceptance tests.
