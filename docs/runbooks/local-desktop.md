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

The default `dev` command prefers http://127.0.0.1:8080. If another
application (including a previous orphan server) occupies that port, it
**automatically selects a free localhost port** and prints the actual URL.
It does **not** terminate unknown processes. The browser opens the selected
URL, so use that URL instead of assuming 8080. Run `dev --port 8080` only
when you specifically require port 8080; explicitly requested ports remain
strict and error if occupied.

Stop with Ctrl-C. The launcher stops the server on termination (SIGTERM)
or terminal hang-up (SIGHUP). On macOS/Linux the launched server also
monitors a private parent-liveness pipe and exits automatically if the
launcher is force-killed (SIGKILL) or crashes, preventing a retained port
from an orphaned **new** dev server. This cannot retroactively stop old
orphan processes started before the fix. If you still want to free 8080
from a pre-fix server on macOS, identify it before stopping it:

~~~bash
lsof -nP -iTCP:8080 -sTCP:LISTEN
ps -p <PID> -o pid,ppid,command
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
Every row now has editable quantity (0–10,000), an inclusion checkbox,
allowed rotation (0°, 180°, or both), and extra piece margin in inches (0–12).
A zero quantity is valid and excludes that pattern from the job even if its
Include checkbox remains checked. The saved checkbox choice and margin remain
untouched, so increasing the quantity reactivates the pattern. Invalid rows
cannot be included; the summary counts only positive included quantities.
The UI has Include all valid and Exclude all convenience controls.

The inventory table starts hidden and becomes visible immediately on upload
via an explicit fresh table-row update (no additional Include/Exclude click).
Fabric inputs are available above the inventory: width, left/right selvedge
reserves, start/end length reserves, global piece gap, optional maximum roll
length (blank = uncapped), and per-model solver time limit. All spatial inputs
are in inches. Width must exceed combined left and right reserves; maximum
length, when specified, must exceed start/end reserves.

The extra per-pattern margin is a uniform **placement keep-out**, not a seam
allowance, and never alters the cutting outline. Future solver semantics:
minimum gap between pieces = global gap + margin of piece A + margin of piece B.
The "Preview job inputs" button shows the validated, normalized job payload.

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
