from __future__ import annotations

from pathlib import Path

import pytest


SAMPLE_NOTE = """\
---
date: 2026-04-16
type: work
category: customer-call
source: meeting
source_artifact: transcript.txt
status: open
needs_review: true
review_notes:
  - Question one
  - Question two
review_responses: []
attendees:
  - Example Name
customer: Acme Corp
topics:
  - example-topic
tags:
  - example-tag
commitments: []
decisions: []
reviewed: false
---

Body paragraph.
"""


@pytest.fixture
def tmp_note(tmp_path: Path) -> Path:
    dst = tmp_path / "sample-note.md"
    dst.write_text(SAMPLE_NOTE)
    return dst
