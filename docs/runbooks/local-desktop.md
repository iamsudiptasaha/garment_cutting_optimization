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
URL, so use that URL instead of assuming 8080. The dev launcher holds a
per-checkout operating-system lock for its entire lifetime. **Running dev
again reuses the already-running URL and launches no additional server or
port**, even if the second command requests a different port. The first
instance owns the selected port until stopped. Run `dev --port 8080` only
when you specifically require port 8080 for the initial instance; explicit
ports error if occupied.

The lock releases automatically after normal exit, crash or SIGKILL.
A stale lock file alone cannot prevent startup; the OS lock is authoritative.
Only one new development server per checkout is permitted. This is separate
from the one-click production LAN host and does not clean up old servers
orphaned before this version.

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

The launcher deliberately **reuses** the existing process if you type
`dev` a second time. Reusing an outdated server or an old browser tab can
make new GUI updates appear to have no effect. After `git pull origin main`
on macOS/Linux, explicitly restart the verified launcher for this checkout:

~~~bash
python -m garment_nesting.app dev --restart
~~~

This sends SIGTERM only to the verified `-m garment_nesting.app dev`
launcher that holds this checkout's advisory lock and waits for it to exit.
If a verified launcher stays stuck during shutdown (observed on macOS), the
explicit `--restart` command escalates to SIGKILL **only after re-checking
that the same PID still owns the project's development lock**. It then
waits for that server's previous port to be released before starting one
replacement server. It never force-stops arbitrary Python processes, and
never silently opens a new port when the previous dev server still occupies
its port.

Diagnostics: a failed restart reports the stored lock path, verified owner
PID, or the exact port remaining occupied. You can inspect the stored owner
without deleting any files:

~~~bash
python - <<'PY'
from pathlib import Path
import json
import subprocess
from garment_nesting import app

lock = app._dev_lock_path(Path(app.__file__).resolve().parent)
state = json.loads(lock.read_text()) if lock.exists() else {}
print("Lock:", lock, "State:", state)
pid = state.get("launcher_pid")
if isinstance(pid, int):
    subprocess.run(["ps", "-p", str(pid), "-o", "pid,ppid,stat,etime,command"])
PY
~~~

On Windows, use Ctrl-C in the old developer terminal and launch `dev`
again (`--restart` is not supported).

Check the URL **printed by the new server**, which may be different from
the old bookmarked URL when port 8080 is occupied. The page now displays
`UI version: <12-character hash>` at the top. The same hash is returned
by `GET /health`. If the version label is missing, the browser is on
an old GUI. If the hash mismatches the console, the tab is talking to a
different process, not the version just launched.

Inputs now have external, larger bold labels, rather than depending on
the tiny floating Quasar placeholders. CI runs a real Chromium acceptance
test: upload the reference SVG, confirm 44 pattern rows actually render
and the numeric controls appear, measure fabric-label font size, change a
quantity to zero and verify the summary updates. A browser screenshot
is uploaded as the `gui-browser-acceptance-3.13` workflow artifact.

Use `--no-browser` for headless tests.

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

The inventory table is always rendered (with empty-state instructions before
upload). On successful upload it receives a fresh list of rows and an explicit
NiceGUI table update, without relying on a visibility toggle or Include/Exclude
click. The file uploader now comes before the editing table, has a compact
height to prevent a tall SVG preview from obscuring the editor, and smoothly
scrolls to “Step 2 · Review and edit pieces” after importing patterns.
Headings, descriptions, input labels and table headers are larger for
shop-floor readability.

Fabric inputs are available above the inventory: width, left/right selvedge
reserves, start/end length reserves, global piece gap, optional maximum roll
length (blank = uncapped), and per-model solver time limit. All spatial inputs
are in inches. Width must exceed combined left and right reserves; maximum
length, when specified, must exceed start/end reserves.

The extra per-pattern margin is a uniform **placement keep-out**, not a seam
allowance, and never alters the cutting outline. The solver validator now
enforces minimum gap between pieces = global gap + margin A + margin B.
The "Preview job inputs" button shows the validated, normalized job payload.

These controls update a **per-browser-session** configuration only. Multiple
uploads with the same SVG filename or group IDs have distinct internal IDs.
Uploaded original files and selection settings are **not saved** across
restarts. The browser-session source bytes are kept in RAM (up to a combined
100 MB per page) so a solver can use precisely the uploaded files; they are
written to short-lived temporary files only during geometry preparation.
The existing `garment-nesting nest` CLI and its output format are unchanged.

## Step 3: solving experiments

Choose **Shelf baseline** (runs with Shapely) and/or **PackingSolver native**
(requires an installed compatible `packingsolver.irregular` wheel). Press
**Run selected solvers**. The computation runs outside the NiceGUI event loop.
The GUI displays each processor's result status, actual used fabric length,
wastage percentage, total placed copies, and a selectable polygon-only preview
of feasible solutions. Complete results are ranked by shortest validated
length; unsupported native environments explicitly show `UNAVAILABLE`.

The new job adapter honors per-pattern quantity, 0°/180° allowed rotations,
the base gap, both pieces' extra margins, the fixed width, left/right selvedge,
start/end reserves, and optional maximum length. The native adapter uses a
conservative global distance of `base_gap + 2 × max(extra_margin)` because
the solver exposes only a uniform item–item spacing parameter. Therefore
native layout quality can be worse than a future truly per-piece solver.
The shelf baseline uses padded bounding rectangles and is also deliberately
conservative; neither result is evidence of a globally optimal marker.

Every candidate must pass an independent Shapely validator checking:
requested counts, allowed rotations, no mirroring, source-identity mappings,
actual polygon intersection, pairwise clearance, usable width and maximum
length. A missing or incomplete placement is `NOT_FOUND` (not proof of
infeasibility). Impossible piece width or an area lower bound can be reported
as `PROVEN_INFEASIBLE` before running a solver. Wastage uses original piece
polygon areas over **full fabric width × total length including start/end
reserves**. No SVG path data is altered.

The displayed result is only a **solver-polygon preview**. Cutting-safe
original Bézier/group-label SVG export, high-resolution PNG/JPEG export from
selected layouts, job persistence and extended algorithm comparison remain
separate future stages. Max total pieces per experiment is 10,000; an
oversized job is rejected rather than silently truncated.

## Security

The initial LAN host uses plain HTTP and has **no authentication**.
Run on a trusted isolated network, never internet port-forward port 8080.
Add operator authorization and persistent job storage before deploying
to general staff. The bundle can execute the PackingSolver and use the
resvg_py renderer without separately installing the Cairo system library.
CI executable smoke tests do not replace real machine/phone acceptance tests.
