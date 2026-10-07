"""Validated identities, bounded documents and immutable evidence writes."""
import hashlib
import json
import math
from pathlib import Path
import re
import uuid
import stat
import unicodedata
import zipfile
import zlib
from io import BytesIO
from .limits import (MAX_ARCHIVE_BYTES, MAX_ARCHIVE_ENTRIES, MAX_ARCHIVE_MEMBER_BYTES,
                     MAX_JSON_DOCUMENT_BYTES, MAX_SOURCE_LINES, MAX_UPLOAD_BYTES)

MAX_UPLOAD = MAX_UPLOAD_BYTES
# Supported predicates can contain 192 comparisons. Leave room for their
# analysis/process wrappers while keeping arbitrary document nesting bounded.
MAX_DOCUMENT_DEPTH = 256
ID = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]{0,79}$')
DEVICES = {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}


class ValidationError(ValueError):
    pass


def require(condition, message):
    if not condition: raise ValidationError(message)


def identity(value):
    require(isinstance(value, str) and ID.fullmatch(value), 'Use an ID beginning with a letter and containing letters, numbers, hyphens or underscores.')
    require(value.upper() not in DEVICES,'Use a portable ID; Windows device names are reserved')
    return value


def path_is_link(path):
    """Treat Windows junctions and symbolic links as redirected filesystem paths."""
    path = Path(path)
    # Import-time environment diagnostics also run on unsupported interpreters.
    # CPython 3.12 supplies is_junction; supported Windows writes always use it.
    return path.is_symlink() or getattr(path, 'is_junction', lambda: False)()


def safe_path(root, relative):
    # Inspect the supplied spelling before resolve() can erase a symlink root
    # or ancestor. This also covers a not-yet-created root below an alias.
    root = Path(root).absolute()
    require(not any(path_is_link(p) for p in [root, *root.parents]), 'Symlink roots are not accepted')
    root = root.resolve()
    require(isinstance(relative, str) and relative and '\\' not in relative and ':' not in relative, 'Invalid relative path')
    require(not any(ord(c)<32 or c in '<>"|?*' for c in relative),'Path contains unsupported control or platform-reserved characters')
    rel = Path(relative)
    require(rel.parts and not rel.is_absolute() and '..' not in rel.parts, 'Path must remain inside its process directory')
    require(all(not p.endswith(('.', ' ')) and p.split('.')[0].upper() not in DEVICES for p in rel.parts),'Path uses a reserved or ambiguous platform filename')
    candidate = root / rel
    require(not any(path_is_link(p) for p in [candidate, *candidate.parents] if p != root.parent), 'Symlink paths are not accepted')
    require(candidate.resolve().is_relative_to(root), 'Path escapes its directory')
    return candidate


def sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()


def encode(value, limit=MAX_JSON_DOCUMENT_BYTES):
    try:
        # The writer must not persist values that the bounded reader cannot
        # recover, or silently coerce object keys into different identities.
        pending = [(value, 0)]
        while pending:
            item, depth = pending.pop()
            require(depth <= MAX_DOCUMENT_DEPTH, 'JSON document nesting exceeds limit')
            if isinstance(item, dict):
                require(all(isinstance(key, str) for key in item), 'JSON object keys must be text')
                pending.extend((child, depth + 1) for pair in item.items() for child in pair)
            elif isinstance(item, (list, tuple)):
                pending.extend((child, depth + 1) for child in item)
        encoder = json.JSONEncoder(ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        output, size = BytesIO(), 1
        for chunk in encoder.iterencode(value):
            raw = chunk.encode('utf-8')
            size += len(raw)
            require(size <= limit, 'JSON document exceeds the configured size limit')
            output.write(raw)
        output.write(b'\n')
        return output.getvalue()
    except ValidationError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ValidationError('Invalid JSON document for persistence') from exc


def decode(data, limit=MAX_JSON_DOCUMENT_BYTES):
    require(isinstance(data, (str, bytes, bytearray)), 'JSON document must be text or bytes')
    try:
        size = len(data.encode('utf-8')) if isinstance(data, str) else len(data)
    except UnicodeError as exc:
        raise ValidationError('JSON document must contain valid UTF-8 text') from exc
    require(size <= limit, 'Document exceeds the configured size limit')
    def pairs(entries):
        result = {}
        for k, v in entries:
            require(k not in result, 'Duplicate JSON key')
            result[k] = v
        return result
    def floating(v):
        n = float(v)
        require(math.isfinite(n), 'Nonfinite numbers are not accepted')
        return n
    try:
        # json.loads(bytes) otherwise auto-detects UTF-16/32, contrary to the
        # UTF-8 source and document contract used by the API and hashes.
        text = data if isinstance(data, str) else bytes(data).decode('utf-8-sig')
        result = json.loads(text, object_pairs_hook=pairs, parse_float=floating, parse_constant=lambda v: require(False, 'Invalid JSON number'))
        # Some JSON parsers accept trees deeper than the encoder or downstream
        # consumers can handle. Bound the persisted document independently of
        # the interpreter recursion setting and reject lone escaped surrogates.
        pending = [(result, 0)]
        while pending:
            value, depth = pending.pop()
            require(depth <= MAX_DOCUMENT_DEPTH, 'JSON document nesting exceeds limit')
            if isinstance(value, str): value.encode('utf-8')
            elif isinstance(value, dict):
                pending.extend((item, depth + 1) for pair in value.items() for item in pair)
            elif isinstance(value, list): pending.extend((item, depth + 1) for item in value)
        return result
    except UnicodeError as exc:
        raise ValidationError('JSON document must contain valid UTF-8 text') from exc
    except (ValueError, TypeError, RecursionError) as exc:
        raise ValidationError('Invalid JSON document') from exc


def write_new(path, data):
    require(isinstance(data, (bytes, bytearray)), 'Evidence data must be bytes')
    data = bytes(data)
    path = Path(path)
    require(not path.exists() and not path_is_link(path), 'Evidence already exists; create a new version')
    require(not any(path_is_link(p) for p in path.parents), 'Symlink output parents are not accepted')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as out: out.write(data)
    return sha(data)


def atomic_json(path, value):
    atomic_bytes(path, encode(value))


def atomic_bytes(path, payload):
    require(isinstance(payload, bytes), 'State payload must be bytes')
    path = Path(path)
    require(not path_is_link(path) and not any(path_is_link(p) for p in path.parents), 'Unsafe state path')
    require(not path.exists() or path.is_file(), 'State destination must be a regular file')
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / ('.' + path.name + '.' + uuid.uuid4().hex)
    created = False
    try:
        with temp.open('xb') as out:
            created = True
            out.write(payload)
        temp.replace(path)
    finally:
        if created: temp.unlink(missing_ok=True)


def checked_zip(data):
    require(isinstance(data, (bytes, bytearray)), 'Archive must be bytes')
    require(len(data) <= MAX_UPLOAD, 'Archive exceeds upload limit')
    archive = None
    try:
        archive = zipfile.ZipFile(BytesIO(data))
        entries = archive.infolist()
        require(len(entries) <= MAX_ARCHIVE_ENTRIES and sum(x.file_size for x in entries) <= MAX_ARCHIVE_BYTES, 'Archive expansion exceeds limit')
        require(len({x.filename for x in entries}) == len(entries), 'Duplicate archive members are not accepted')
        identities = {}
        for x in entries:
            require(not x.filename.startswith(('/', '\\')) and '..' not in Path(x.filename).parts and '\\' not in x.filename, 'Unsafe archive path')
            name = x.filename[:-1] if x.is_dir() else x.filename
            parts = name.split('/')
            require(all(part and part not in {'.', '..'} for part in parts), 'Archive paths must have canonical member identities')
            require(not any(ord(c) < 32 or c in ':<>"|?*' for c in name), 'Archive path uses unsupported characters')
            require(all(not p.endswith(('.', ' ')) and p.split('.')[0].upper() not in DEVICES for p in parts), 'Archive path uses a reserved platform filename')
            key = unicodedata.normalize('NFC', name).casefold()
            require(key not in identities, 'Archive members have colliding portable identities')
            identities[key] = x.is_dir()
            kind = stat.S_IFMT(x.external_attr >> 16)
            require(kind in {0, stat.S_IFREG, stat.S_IFDIR}, 'Archive members must be regular files or directories')
            require(not x.is_dir() or x.file_size == 0, 'Archive directory contains unexpected data')
            require(x.file_size <= MAX_ARCHIVE_MEMBER_BYTES, 'Archive member exceeds limit')
            # Read every member within the expansion budget so CRC/compression
            # failures cannot bypass the gate by using a non-XML filename.
            payload = archive.read(x)
            if x.filename.lower().endswith(('.xml', '.rels')):
                # Detect declarations in UTF-16/32 as well as ordinary UTF-8.
                body = payload.replace(b'\x00',b'').upper()
                require(b'<!DOCTYPE' not in body and b'<!ENTITY' not in body, 'XML declarations/entities are not accepted')
        for key in identities:
            require(all(identities.get(parent.as_posix(), True) for parent in Path(key).parents if parent.as_posix() != '.'),
                    'Archive member is also a parent file')
        return archive
    except ValidationError:
        if archive is not None: archive.close()
        raise
    except (zipfile.BadZipFile, OSError, ValueError, TypeError, RuntimeError, NotImplementedError, zlib.error, EOFError) as exc:
        if archive is not None: archive.close()
        raise ValidationError('Invalid ZIP/XLSX document') from exc
