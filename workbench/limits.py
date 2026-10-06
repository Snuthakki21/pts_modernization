"""Independent bounds for repository input, browser transport and JSON state.

These limits are safety ceilings, not a promise that every export near a ceiling
will fit in memory or have a supported conversion. Source analysis retains text
and structured evidence, so large exports need additional memory and disk space.
"""
import re

MAX_SOURCE_FILES = 10_000
MAX_SOURCE_ENTRIES = 40_000
MAX_SOURCE_FILE_BYTES = 16 * 1024 * 1024
MAX_SOURCE_BYTES = 512 * 1024 * 1024
MAX_SOURCE_LINES = 2_000_000
MAX_WORKSPACE_ENTRIES = 100_000

# A browser upload is a separate transport from local Endeavor folder intake.
MAX_UI_SOURCE_BYTES = 32 * 1024 * 1024
MAX_HTTP_BODY_BYTES = 128 * 1024 * 1024
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_JSON_DOCUMENT_BYTES = 128 * 1024 * 1024

MAX_ARCHIVE_ENTRIES = 300
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_MEMBER_BYTES = 8 * 1024 * 1024

_LINE_END = re.compile(r'\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]')


def source_line_count(text):
    """Count physical lines like str.splitlines(), without allocating a list."""
    count, end = 0, 0
    for match in _LINE_END.finditer(text):
        count += 1
        end = match.end()
    return count + bool(text and end < len(text))
