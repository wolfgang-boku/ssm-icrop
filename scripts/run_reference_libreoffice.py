"""Run a workbook's iCrops macro in headless LibreOffice and export its DailyO sheet.

Microsoft Excel is the engine the VBA model was written for, and the committed
reference output came from a run in Excel. LibreOffice Basic runs the same
macro after three adjustments that change no model calculation (see
`patch_vba_source` and `numeric_text_cells`). It was verified against the Excel
reference output, and that verification holds only for the code paths the
four reference scenarios run: see "Reference runs in LibreOffice" in
docs/verification.md before relying on output from this script.

The workbook is copied to a temporary directory and never saved; the weather
workbooks are copied next to it and the Location sheet is pointed at the
copies. Nothing in the repository is modified.

Run it with the system Python that has LibreOffice's UNO bridge (python3-uno),
not with .venv, whose Python cannot import `uno`. It uses the standard
library only.

Usage:
    /usr/bin/python3 scripts/run_reference_libreoffice.py \\
        --override "Manag!G89=1e300" \\
        -o /tmp/dailyo_libreoffice.csv \\
        --compare data/verification/2022-05-29/wheat_gorgan_reference_output.csv
"""

import argparse
import csv
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DEFAULT_WORKBOOK = REPO_ROOT / "SSM-iCrop" / "SSM_iCrop__2022_05_29_verification.xlsm"
DEFAULT_WEATHER_DIR = REPO_ROOT / "SSM-iCrop" / "Weather"

# DailyPrintOut identifier columns (sName .. Crop); compared as text, not numbers.
N_ID_COLUMNS = 5

WRAPPER_MODULE = "LORunWrapper"
WRAPPER_SOURCE = """Option VBASupport 1
Function RunICrops() As String
    On Error GoTo failed
    iCrops
    RunICrops = "OK"
    Exit Function
failed:
    RunICrops = "VBA error " & Err.Number & ": " & Err.Description
End Function
"""


# --- Pure helpers (unit-tested in tests/test_run_reference_libreoffice.py) ---

def patch_vba_source(source: str) -> tuple[str, dict[str, int]]:
    """Adapt the macro source to LibreOffice Basic without changing any calculation.

    1. `Pi` is a read-only built-in constant in LibreOffice Basic; VBA has no such
       constant, and iCrop.vba assigns its own value, `Pi = 3.141592654`
       (iCrop.vba:339, :462, :622). Assigning to it stops LibreOffice with
       error 382, so every `Pi` is renamed to `PiV`. The value stays
       3.141592654 because the assignments are renamed too.
    2. After `wb.Close False` (end of each scenario, iCrop.vba:100), LibreOffice
       returns an unusable object when the next scenario reopens the same
       weather workbook, and `wb.Worksheets("Sheet1")` fails. The close is
       commented out; the weather workbook is opened read-only and only read,
       so leaving it open changes no value.
    """
    if re.search(r"\bPiV\b", source, flags=re.IGNORECASE):
        raise ValueError("source already contains 'PiV'; renaming Pi would merge two names")
    patched, n_pi = re.subn(r"\bPi\b", "PiV", source, flags=re.IGNORECASE)
    patched, n_close = re.subn(
        r"(?im)^(\s*)(wb\.Close\s+False)", r"\1'\2   ' disabled for LibreOffice", patched
    )
    if n_pi == 0 or n_close == 0:
        raise ValueError(
            f"expected iCrop.vba's Pi assignments and wb.Close; found {n_pi} Pi, "
            f"{n_close} wb.Close. The macro differs from the one this script was "
            "verified with; check docs/verification.md before adapting the patch."
        )
    return patched, {"Pi renamed": n_pi, "wb.Close disabled": n_close}


def input_sheets(source: str) -> list[str]:
    """The sheets of its own workbook the macro reads, in order of first use.

    iCrop.vba reads every input through `ThisWorkbook.Worksheets("<name>")`;
    the sheets it addresses by code name (`Sheet4.Cells(...)` and so on) it
    only writes to. Deriving the list from the source keeps the check for
    numbers stored as text complete if a later macro reads another sheet.
    """
    names = re.findall(r'ThisWorkbook\.Worksheets\("([^"]+)"\)', source, flags=re.IGNORECASE)
    return list(dict.fromkeys(names))


def column_letters(index: int) -> str:
    """Spreadsheet column letters for a 0-based column index (0 -> A, 26 -> AA)."""
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters


# Text that LibreOffice Basic may convert to a number: a decimal number with
# '.' or ',' as decimal separator, optionally grouped in thousands ('1,000.5',
# '1.000,5') depending on the locale, with an E or D exponent; or a VBA hex or
# octal literal (&H1F, &O17). Percentages, dates, times and space-grouped
# numbers are not flagged. Python's float() would accept 'nan', 'inf' and '1_0'
# instead, which are no numbers here.
_NUMERIC_TEXT = re.compile(
    r"[+-]?(\d{1,3}([.,]\d{3})+([.,]\d*)?|\d+([.,]\d*)?|[.,]\d+)([eEdD][+-]?\d+)?"
    r"|&[hH][0-9A-Fa-f]+|&[oO][0-7]+")


def is_numeric_text(value) -> bool:
    """True for a string that LibreOffice may convert to a number."""
    return isinstance(value, str) and _NUMERIC_TEXT.fullmatch(value.strip()) is not None


def numeric_text_cells(sheet: str, rows) -> list[str]:
    """Cells of `rows` (a sheet's data array from A1) that hold a number as text.

    VBA and LibreOffice Basic compare such a cell differently. Read into an
    undeclared Variant it stays a String; VBA ranks every number below every
    string, so `FTSWRZ <= IRGLVL` is always true (docs/verification.md,
    `IRGLVL` in `Taj1-Nlim`), while LibreOffice converts the string and compares
    numerically. Which result VBA gives depends on the operator, so the script
    cannot emulate it in general: each such cell needs an explicit --override.
    """
    return [
        f"{sheet}!{column_letters(c)}{r + 1}"
        for r, row in enumerate(rows)
        for c, value in enumerate(row)
        if is_numeric_text(value)
    ]


def parse_override(text: str) -> tuple[str, str, float]:
    """'Manag!G89=1e300' -> ('Manag', 'G89', 1e300).

    The sheet name is matched case-insensitively against the workbook later
    (`_resolve_sheet`).
    """
    m = re.fullmatch(r"\s*([^!]+?)\s*!\s*([A-Za-z]{1,3})([1-9][0-9]*)\s*=\s*(\S+)\s*",
                     text)
    if not m:
        raise argparse.ArgumentTypeError(f"expected SHEET!CELL=NUMBER, got {text!r}")
    sheet, column, row, number = m.groups()
    try:
        value = float(number)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {number!r}") from None
    if not math.isfinite(value):
        raise argparse.ArgumentTypeError(f"not a finite number: {number!r}")
    return sheet, f"{column.upper()}{int(row)}", value


def csv_value(value):
    """Format a cell value as the openpyxl export of docs/verification.md does.

    openpyxl returns whole numbers stored in the workbook as int, other numbers
    as float (written with repr, full precision), and blank cells as None.
    LibreOffice returns every number as float and blank cells as "". Only
    whole numbers a double holds exactly (|x| < 2**53) are written as int.
    """
    if isinstance(value, float):
        if value.is_integer() and abs(value) < 2**53:
            return str(int(value))
        return repr(value)
    return value


def dailyo_rows(data) -> tuple[list[str], list[list]]:
    """Header and CSV rows of a DailyO data array (row 0 is the header).

    Blank cells right of the last header are not columns; rows with a blank
    scenario name are not output (the gaps between the 500-row blocks).
    """
    header = list(data[0])
    while header and header[-1] == "":
        header.pop()
    rows = [[csv_value(v) for v in row[:len(header)]] for row in data[1:] if row[0] != ""]
    return header, rows


# --- Comparison with a reference CSV (standard library only) ---

def _diff(a: str, b: str) -> float:
    """Absolute difference of two CSV cells.

    Equal text is 0 (blank vs blank included); text that differs and is not
    two finite numbers (blank vs number, '#N/A', 'nan') is inf.
    """
    if a == b:
        return 0.0
    try:
        x, y = float(a), float(b)
    except ValueError:
        return math.inf
    return abs(x - y) if math.isfinite(x) and math.isfinite(y) else math.inf


def _within(a: str, b: str, d: float, tolerance: float, rel_tolerance: float) -> bool:
    """Whether difference `d` of cells `a`, `b` is within the absolute or relative bound.

    The relative bound scales with the value: LibreOffice's rounding noise is a
    few units in the last place, which is 2.3e-13 at 1400 but 1.8e-12 at 8192.
    """
    if d <= tolerance:
        return True
    if math.isinf(d):
        return False
    return d <= rel_tolerance * max(abs(float(a)), abs(float(b)))


def _by_scenario(rows) -> dict[str, list]:
    groups: dict[str, list] = {}
    for row in rows:
        groups.setdefault(row[0], []).append(row)
    return groups


def _compare_scenario(header, a, b, tolerance: float, rel_tolerance: float) -> bool:
    if len(a) != len(b):
        print("   row counts differ; not compared")
        return False
    id_mismatch = sum(ra[:N_ID_COLUMNS] != rb[:N_ID_COLUMNS] for ra, rb in zip(a, b))
    results, over = [], []
    for c in range(N_ID_COLUMNS, len(header)):
        pairs = [(ra[c], rb[c]) for ra, rb in zip(a, b)]
        diffs = [(x, y, d) for x, y in pairs if (d := _diff(x, y)) > 0]
        results.append((max((d for _, _, d in diffs), default=0.0), header[c], len(diffs)))
        if not all(_within(x, y, d, tolerance, rel_tolerance) for x, y, d in diffs):
            over.append(header[c])
    identical = sum(1 for worst, _, _ in results if worst == 0)
    print(f"   identifier mismatches: {id_mismatch} rows; "
          f"numeric columns identical: {identical}/{len(results)}")
    for worst, name, n_diff in sorted(results, reverse=True)[:10]:
        if worst > 0:
            print(f"   {name:8s} max |diff| {worst:.3g} ({n_diff} rows differ)")
    if over:
        print(f"   outside tolerance: {', '.join(over)}")
    return id_mismatch == 0 and not over


def compare_csv(run_csv: Path, reference_csv: Path, tolerance: float,
                rel_tolerance: float = 0.0) -> bool:
    """Print, per scenario, the largest absolute difference per column.

    Returns True when both files hold the same columns, scenarios, row counts
    and identifiers, and every value differs by at most `tolerance` or by at
    most `rel_tolerance` times its magnitude.
    """
    def load(path):
        with open(path, newline="") as f:
            rows = list(csv.reader(f))
        return rows[0], rows[1:]

    header, run_rows = load(run_csv)
    ref_header, ref_rows = load(reference_csv)
    if header != ref_header:
        print("columns differ from the reference; not compared")
        return False
    short = [r for r in run_rows + ref_rows if len(r) != len(header)]
    if short:
        print(f"{len(short)} rows do not have {len(header)} fields; not compared")
        return False
    ref, run = _by_scenario(ref_rows), _by_scenario(run_rows)
    ok = True
    for scn in (s for s in run if s not in ref):
        print(f"== {scn}: only in this run, not in the reference")
        ok = False
    for scn, a in ref.items():
        b = run.get(scn, [])
        print(f"== {scn}: reference {len(a)} rows, this run {len(b)} rows")
        ok &= _compare_scenario(header, a, b, tolerance, rel_tolerance)
    print("comparison: " + ("passed" if ok else "FAILED")
          + f" (tolerance {tolerance:g}, relative {rel_tolerance:g})")
    return ok


# --- LibreOffice process ---

def _exit_status(proc: subprocess.Popen):
    """How `proc` ended ('exit status 1', 'signal 9'), or None, without reaping it."""
    info = os.waitid(os.P_PID, proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    if info is None:
        return None
    if info.si_code == os.CLD_EXITED:
        return f"exit status {info.si_status}"
    return f"signal {info.si_status}"


def _kill_group(proc: subprocess.Popen) -> None:
    """Kill the process group `proc` leads (soffice and its child soffice.bin).

    Safe only while `proc` is not reaped: an unreaped (zombie) group leader
    keeps its process group ID reserved, so the signal cannot reach a group
    that reused the ID. Hence `_exit_status` instead of `proc.poll()`, and
    `proc.wait()` only after the last kill.
    """
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass  # already gone


def _connect(pipe: str, proc: subprocess.Popen, timed_out: threading.Event,
             timeout: float):
    import uno

    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", local)
    deadline = time.monotonic() + timeout
    while True:
        try:
            return resolver.resolve(f"uno:pipe,name={pipe};urp;StarOffice.ComponentContext")
        except Exception:
            if timed_out.is_set():
                raise
            status = _exit_status(proc)
            if status is not None:
                sys.exit(f"soffice ended ({status}) before accepting a connection")
            if time.monotonic() > deadline:
                raise
            time.sleep(0.5)


class _LibreOffice:
    """A headless LibreOffice with its own profile; `with` yields its Desktop.

    soffice is a launcher that starts soffice.bin as a child, so it runs in a
    process group of its own and is killed as a group: after `timeout`
    seconds (a macro that never ends, e.g. `Do Until MAT = 1` past the last
    weather row, would otherwise block forever), and on exit, before the
    caller removes the profile directory.

    A class rather than a @contextmanager generator: contextlib sets
    `__traceback__` on an exception passing through, which UNO exceptions
    refuse, and the real error would be lost.
    """

    def __init__(self, soffice: str, profile: Path, timeout: float):
        self.soffice, self.profile, self.timeout = soffice, profile, timeout
        self.timed_out = threading.Event()
        self.desktop = None

    def __enter__(self):
        pipe = f"icrop_lo_{uuid.uuid4().hex[:8]}"
        self.proc = subprocess.Popen(
            [self.soffice, f"-env:UserInstallation={self.profile.as_uri()}",
             "--headless", "--invisible", "--norestore", "--nologo", "--nodefault",
             f"--accept=pipe,name={pipe};urp;"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        self.watchdog = threading.Timer(self.timeout, self._on_timeout)
        self.watchdog.start()
        try:
            ctx = _connect(pipe, self.proc, self.timed_out, timeout=60)
            self.desktop = ctx.ServiceManager.createInstanceWithContext(
                "com.sun.star.frame.Desktop", ctx)
        except BaseException as exc:
            self.__exit__(type(exc), exc, exc.__traceback__)
            raise
        return self.desktop

    def _on_timeout(self):
        self.timed_out.set()  # before the kill, so the main thread sees why
        _kill_group(self.proc)

    def __exit__(self, exc_type, exc, tb):
        # The watchdog stays armed until LibreOffice is gone: terminate() is a
        # UNO call that can block too.
        try:
            if self.desktop is not None:
                self.desktop.terminate()
        except Exception:
            pass  # the bridge is gone when LibreOffice has exited
        deadline = time.monotonic() + 30
        while _exit_status(self.proc) is None and time.monotonic() < deadline:
            time.sleep(0.2)
        _kill_group(self.proc)
        # Disarm the watchdog, and wait for a callback already running, before
        # reaping: after proc.wait() the group ID may belong to someone else.
        self.watchdog.cancel()
        self.watchdog.join()
        self.proc.wait()
        if self.timed_out.is_set() and exc_type is not None and issubclass(exc_type, Exception):
            sys.exit(f"LibreOffice run did not finish within {self.timeout:g} s; killed")
        return False


# --- Work on the documents ---

def _prop(name, value):
    from com.sun.star.beans import PropertyValue

    p = PropertyValue()
    p.Name, p.Value = name, value
    return p


def _load(desktop, path: Path, run_macros: bool):
    import uno

    props = [_prop("Hidden", True)]
    if run_macros:
        # MacroExecutionMode 4 = ALWAYS_EXECUTE_NO_WARN: run the document's
        # macros without the security dialog a headless instance cannot show.
        props.append(_prop("MacroExecutionMode", 4))
    else:
        props.append(_prop("ReadOnly", True))
    return desktop.loadComponentFromURL(
        uno.systemPathToFileUrl(str(path)), "_blank", 0, tuple(props))


def _used_end(sheet):
    cursor = sheet.createCursor()
    cursor.gotoEndOfUsedArea(False)
    return cursor.RangeAddress


def _used_data(sheet):
    end = _used_end(sheet)
    return sheet.getCellRangeByPosition(0, 0, end.EndColumn, end.EndRow).getDataArray()


def _resolve_sheet(doc, name: str) -> str:
    """The workbook's own spelling of sheet `name`, matched case-insensitively."""
    for actual in doc.Sheets.getElementNames():
        if actual.lower() == name.lower():
            return actual
    sys.exit(f"no sheet {name!r} in the workbook")


def _find_macro(doc):
    """(library name, library, module name, source) of the module with iCrops."""
    libs = doc.BasicLibraries
    for lib_name in libs.getElementNames():
        libs.loadLibrary(lib_name)
        lib = libs.getByName(lib_name)
        for module in lib.getElementNames():
            source = lib.getByName(module)
            if re.search(r"(?im)^\s*Sub\s+iCrops\s*\(", source):
                return lib_name, lib, module, source
    sys.exit("no module with 'Sub iCrops()' found in the workbook")


def _apply_overrides(doc, sheet_names, overrides) -> None:
    """Refuse numbers stored as text that no override covers; apply the overrides.

    `sheet_names` are the sheets the macro reads by name. The first sheet is
    checked too: the macro reads the scenario block from it by position,
    `Worksheets(1)` (iCrop.vba:37, :39).
    """
    names = [_resolve_sheet(doc, n) for n in sheet_names]
    names = list(dict.fromkeys(names + [doc.Sheets.getByIndex(0).Name]))
    found = []
    for name in names:
        found += numeric_text_cells(name, _used_data(doc.Sheets.getByName(name)))
    resolved = [(_resolve_sheet(doc, s), c, v) for s, c, v in overrides]
    missing = sorted(set(found) - {f"{s}!{c}" for s, c, _ in resolved})
    if missing:
        sys.exit("numbers stored as text, which VBA and LibreOffice compare differently "
                 "(see numeric_text_cells): " + ", ".join(missing)
                 + "\nGive each an --override with the value that reproduces VBA's result.")
    for sheet, cell, value in resolved:
        target = doc.Sheets.getByName(sheet).getCellRangeByName(cell)
        print(f"override: {sheet}!{cell} {target.getString()!r} -> {value!r}")
        target.setValue(value)


def _check_weather_workbook(desktop, path: Path) -> None:
    """Refuse numbers stored as text in Sheet1, the sheet the macro reads."""
    weather = _load(desktop, path, run_macros=False)
    try:
        data = _used_data(weather.Sheets.getByName("Sheet1"))
    finally:
        weather.close(True)
    found = numeric_text_cells(f"{path.name}:Sheet1", data)
    if found:
        sys.exit("numbers stored as text in the weather workbook, which VBA and "
                 "LibreOffice compare differently: " + ", ".join(found))


def _point_weather_files(doc, desktop, weather_dir: Path, workdir: Path) -> None:
    """Copy each scenario's weather workbook to `workdir`; point Location at it.

    The Location sheet holds absolute Windows paths (column D of row
    LocRowNo + 2, iCrop.vba:52). Only the file name is used, so two different
    paths with the same file name are refused rather than merged.
    """
    # The scenario block is read from the first sheet by position, the
    # scenario rows from "Run" by name, as the macro does (iCrop.vba:37-48).
    first_sheet = doc.Sheets.getByIndex(0)
    first_row = int(first_sheet.getCellRangeByName("B5").getValue())
    n_scenarios = int(first_sheet.getCellRangeByName("B6").getValue())
    run, location = doc.Sheets.getByName("Run"), doc.Sheets.getByName("Location")
    sources: dict[str, str] = {}   # file name -> path given in Location
    done_rows: set[int] = set()
    for i in range(n_scenarios):
        loc_row_no = int(run.getCellByPosition(1, first_row - 1 + i).getValue())
        if loc_row_no in done_rows:
            continue
        done_rows.add(loc_row_no)
        cell = location.getCellByPosition(3, loc_row_no + 1)  # D(LocRowNo + 2)
        original = cell.getString()
        name = re.split(r"[\\/]", original)[-1]
        target = workdir / name
        if name not in sources:
            source = weather_dir / name
            if not source.is_file():
                sys.exit(f"weather workbook {name!r} (Location row {loc_row_no + 2}) "
                         f"not found in {weather_dir}")
            shutil.copy2(source, target)
            _check_weather_workbook(desktop, target)
            sources[name] = original
        elif sources[name] != original:
            sys.exit(f"two weather paths share the file name {name!r}: "
                     f"{sources[name]!r} and {original!r}")
        cell.setString(str(target))


def _install_wrapper(doc, lib_name: str, lib):
    """Add a function that runs iCrops and returns 'OK' or the VBA error."""
    if lib.hasByName(WRAPPER_MODULE):
        lib.removeByName(WRAPPER_MODULE)
    lib.insertByName(WRAPPER_MODULE, WRAPPER_SOURCE)
    return doc.getScriptProvider().getScript(
        f"vnd.sun.star.script:{lib_name}.{WRAPPER_MODULE}.RunICrops"
        "?language=Basic&location=document")


def _clear_below_header(sheet) -> None:
    end = _used_end(sheet)
    if end.EndRow >= 1:
        # Flags: VALUE | DATETIME | STRING | FORMULA.
        sheet.getCellRangeByPosition(0, 1, end.EndColumn, end.EndRow).clearContents(
            1 | 2 | 4 | 16)


def _run_in_document(doc, desktop, weather_dir, workdir, overrides, out_csv) -> None:
    lib_name, lib, module, source = _find_macro(doc)
    _apply_overrides(doc, input_sheets(source), overrides)
    _point_weather_files(doc, desktop, weather_dir, workdir)
    daily = doc.Sheets.getByName("DailyO")
    _clear_below_header(daily)  # so the export holds this run only

    patched, report = patch_vba_source(source)
    print("patch: " + ", ".join(f"{k} {v}" for k, v in report.items()))
    lib.replaceByName(module, patched)
    script = _install_wrapper(doc, lib_name, lib)

    start = time.monotonic()
    result = script.invoke((), (), ())[0]
    print(f"macro: {result} ({time.monotonic() - start:.1f} s)")
    if result != "OK":
        sys.exit(1)

    header, rows = dailyo_rows(_used_data(daily))
    if not rows:
        sys.exit("the macro wrote no rows to DailyO")
    with open(out_csv, "w", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows, {len(header)} columns to {out_csv}")


def run_workbook(workbook: Path, weather_dir: Path, overrides, out_csv: Path,
                 soffice: str, timeout: float) -> None:
    version = subprocess.run([soffice, "--version"], capture_output=True, text=True,
                             check=True).stdout.strip()
    print(f"engine: {version}")
    with tempfile.TemporaryDirectory(prefix="icrop_lo_") as tmp:
        workdir = Path(tmp)
        book = workdir / workbook.name
        shutil.copy2(workbook, book)
        with _LibreOffice(soffice, workdir / "profile", timeout) as desktop:
            doc = _load(desktop, book, run_macros=True)
            try:
                _run_in_document(doc, desktop, weather_dir, workdir, overrides, out_csv)
            finally:
                doc.close(True)  # never stored


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("workbook", nargs="?", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("-o", "--output", type=Path, required=True,
                        help="CSV file for the DailyO rows")
    parser.add_argument("--weather-dir", type=Path, default=DEFAULT_WEATHER_DIR,
                        help="directory holding the weather workbooks (.xls)")
    parser.add_argument("--override", type=parse_override, action="append", default=[],
                        metavar="SHEET!CELL=NUMBER",
                        help="set an input cell to a number in the copy (repeatable)")
    parser.add_argument("--compare", type=Path, metavar="REFERENCE_CSV",
                        help="compare with a reference CSV; exit 1 if they disagree")
    parser.add_argument("--tolerance", type=float, default=1e-12,
                        help="largest absolute difference --compare accepts (default "
                             "1e-12: both engines run the same macro, and LibreOffice "
                             "agreed with Excel to 2.3e-13)")
    parser.add_argument("--rel-tolerance", type=float, default=1e-14,
                        help="relative bound --compare also accepts, times the value's "
                             "magnitude (default 1e-14, about 45 units in the last place)")
    parser.add_argument("--timeout", type=float, default=600,
                        help="seconds before the LibreOffice run is killed (default 600)")
    parser.add_argument("--soffice", default="soffice")
    args = parser.parse_args()

    run_workbook(args.workbook.resolve(), args.weather_dir.resolve(), args.override,
                 args.output, args.soffice, args.timeout)
    if args.compare and not compare_csv(args.output, args.compare, args.tolerance,
                                        args.rel_tolerance):
        sys.exit(1)


if __name__ == "__main__":
    main()
