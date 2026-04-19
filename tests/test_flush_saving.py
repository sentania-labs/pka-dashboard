"""Static-analysis test for the flushDirtyTextareas guard in app/static/todo.js.

Background: a fast tab switch can cancel an in-flight PATCH save, leaving the
textarea's data-save-status as 'saving' (not 'dirty'). The
visibilitychange->sendBeacon flush must re-send those 'saving' textareas too,
otherwise the edit is silently lost. The server's mtime guard makes the
double-send idempotent.

We have no browser runtime in pytest, so this test reads todo.js as text and
asserts the guard line in flushDirtyTextareas references BOTH 'dirty' and
'saving'. It's a coarse check, but it locks in the regression fix so a future
refactor cannot silently drop 'saving' from the guard.
"""
from pathlib import Path


TODO_JS = Path(__file__).resolve().parent.parent / "app" / "static" / "todo.js"


def test_flush_dirty_textareas_guard_includes_dirty_and_saving():
    source = TODO_JS.read_text()
    lines = source.splitlines()

    start = next(
        (i for i, line in enumerate(lines) if "function flushDirtyTextareas" in line),
        None,
    )
    assert start is not None, "flushDirtyTextareas function not found in todo.js"

    guard_line = None
    for line in lines[start : start + 20]:
        if "saveStatus" in line and "return" in line:
            guard_line = line
            break

    assert guard_line is not None, (
        "Could not locate the saveStatus guard line inside flushDirtyTextareas"
    )
    assert "'dirty'" in guard_line, (
        f"Guard line must reference 'dirty'; got: {guard_line!r}"
    )
    assert "'saving'" in guard_line, (
        f"Guard line must reference 'saving' so mid-flight saves cancelled by "
        f"tab switch are re-sent; got: {guard_line!r}"
    )
