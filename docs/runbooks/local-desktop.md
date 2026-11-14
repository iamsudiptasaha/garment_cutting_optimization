# Local development and LAN desktop hosting

## Developer setup
In an activated Python 3.13 virtual environment, install the GUI and
existing input, geometry, processor and output dependencies:

~~~bash
python -m pip install -e ".[dev,geometry,solver,output,app]"
python -m garment_nesting.app dev
~~~

The module also re-enters via the __mp_main__ process during NiceGUI hot reload.\nThe development launcher accepts --no-browser for headless testing.\n\nOpen http://127.0.0.1:8080 in your browser. The NiceGUI development server
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

The browser accepts multiple SVG files and validates each cutting group
through the existing input and geometry layer without changing the source.
Every row now has editable quantity (1–10,000), inclusion checkbox and
allowed rotation (0°, 180°, or both). Invalid rows are disabled and excluded;
the summary shows actual included patterns and total multiplied pieces.
The UI has Include all valid and Exclude all convenience controls.

These controls update a **per-browser-session** configuration only. Multiple
uploads with the same SVG filename or group IDs have distinct internal IDs.
Uploaded original files and selection settings are **not saved** across
restarts, and they do not yet affect the PackingSolver CLI adapter.
The pure `selected_job_rows` function provides a validated source-qualified
configuration for the future plugin-based experiment runner. Solver plugins,
comparison and selected-result export are still pending.

## Security

The initial LAN host uses plain HTTP and has **no authentication**.
Run on a trusted isolated network, never internet port-forward port 8080.
Add operator authorization and persistent job storage before deploying
to general staff. The bundle can execute the PackingSolver and use the
resvg_py renderer without separately installing the Cairo system library.
CI executable smoke tests do not replace real machine/phone acceptance tests.
