# Local development and LAN desktop hosting

## Developer setup
In an activated Python 3.13 virtual environment, install the GUI and
existing input, geometry, processor and output dependencies:

~~~bash
python -m pip install -e ".[dev,geometry,solver,output,app]"
python -m garment_nesting.app dev
~~~

The development command supervises a separate reload-disabled NiceGUI
server. It restarts the server when application Python files change, avoiding
NiceGUI's multiprocessing reload issue with `python -m`.

Open http://127.0.0.1:8080. Stop with Ctrl-C. The watcher also stops the
child server on termination (SIGTERM) or terminal hang-up (SIGHUP).
If port 8080 is already in use, it explains the conflict instead of creating
another orphaned process. On macOS, identify an old listener with:

~~~bash
lsof -nP -iTCP:8080 -sTCP:LISTEN
~~~

After merging changes, run `git pull origin main` and restart
`python -m garment_nesting.app dev`. Use `--no-browser` for headless tests.

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
