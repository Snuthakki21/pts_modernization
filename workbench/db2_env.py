"""Load the fixed private Db2 .env without executing or expanding its contents.

Only documented DB2 fields and exact shared Zowe fields are accepted. Zowe
fields are ignored by Db2 settings, never exported or expanded. The
optional env_file argument is for embedding/tests and the gateway's explicit
--env-file selection. The retained fallback uses DEFAULT_ENV_FILE; no path
environment variable exists. Never use values or ODBC strings as diagnostics.
"""
from .domain import path_is_link
from dataclasses import dataclass, field
import ipaddress
import os
from pathlib import Path, PureWindowsPath
import re
import ssl as tls
import stat
from typing import Mapping

from .domain import ValidationError, require

DEFAULT_ENV_FILE = Path(__file__).resolve().parents[1] / 'tools/dq3g_mcp/.env'
KEYS = frozenset({'DB2_LOCATION_NAME', 'DB2_HOSTNAME', 'DB2_PORT', 'DB2_DATABASE',
                  'DB2_USERNAME', 'DB2_PASSWORD', 'DB2_SSL_CONNECTION',
                  'DB2_SSL_SERVER_CERTIFICATE', 'DB2_SSL_CERT_LOCATION', 'DB2_QUERY_ROW_LIMIT'})
ZOWE_KEYS = frozenset({'ZOWE_ENVIRONMENT', 'ZOWE_DEV_HOST', 'ZOWE_DEV_PORT',
                       'ZOWE_PROD_HOST', 'ZOWE_PROD_PORT', 'ZOWE_TSO_ACCOUNT',
                       'ZOWE_TSO_CODE_PAGE', 'ZOWE_TSO_LOGON_PROCEDURE',
                       'ZOWE_CA_CERTIFICATE', 'ZOWE_USERNAME', 'ZOWE_PASSWORD'})
WORKSPACE_KEYS = KEYS | ZOWE_KEYS
MAX_ENV_BYTES = 65536
MAX_CERT_BYTES = 1024 * 1024
MAX_ROWS = 500000


@dataclass(frozen=True)
class Db2Settings:
    location: str
    database: str
    host: str
    port: int
    ssl: bool
    certificate: Path
    username: str = field(repr=False)
    password: str = field(repr=False)
    row_limit: int = MAX_ROWS


def _path(path: Path) -> Path:
    path = path.absolute()
    require('..' not in path.parts and not path_is_link(path)
            and not any(path_is_link(parent) for parent in path.parents),
            'Db2 local configuration paths must not contain traversal or symbolic links')
    return path


def _read(path: Path, maximum: int, *, missing_ok: bool = False) -> bytes:
    """Bound actual reads as well as stat; refuse links and nonregular files."""
    try:
        path = _path(path)
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
        try:
            descriptor = os.open(path, flags)
        except FileNotFoundError:
            if missing_ok:
                return b''
            raise
        with os.fdopen(descriptor, 'rb') as stream:
            info = os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_size <= maximum,
                    'Db2 local configuration requires a bounded regular file')
            value = stream.read(maximum + 1)
            require(len(value) <= maximum, 'Db2 local configuration exceeds its byte bound')
            return value
    except OSError:
        raise ValidationError('Db2 local configuration file is unavailable or unsafe') from None


def _parse(content: bytes, *, allowed_keys: frozenset[str] = KEYS) -> dict[str, str]:
    try:
        text = content.decode('utf-8')
    except UnicodeError:
        raise ValidationError('Db2 environment file must contain UTF-8 text') from None
    # CRLF is accepted; other control characters and multiline values are not.
    text = text.replace('\r\n', '\n')
    require(not any((ord(char) < 32 and char not in '\n\t') or ord(char) == 127 for char in text),
            'Db2 environment file contains unsupported control characters')
    lines = text.split('\n')
    require(len(lines) <= 128, 'Db2 environment file exceeds its line bound')
    values = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        match = re.fullmatch(r'([A-Z][A-Z0-9_]*)\s*=\s*(.*)', line)
        require(match is not None, 'Db2 environment file requires one literal KEY=value per line')
        key, value = match.groups()
        require(key in allowed_keys and key not in values,
                'Db2 environment file contains an unknown or duplicate field')
        if value.startswith(('"', "'")):
            quote = value[0]
            end = value.find(quote, 1)
            require(end != -1 and (not value[end + 1:].strip() or value[end + 1:].lstrip().startswith('#')),
                    'Db2 environment file contains an invalid quoted value')
            value = value[1:end]
        else:
            # A whitespace-delimited # starts a comment; embedded # is literal.
            value = re.split(r'\s+#', value, maxsplit=1)[0].rstrip()
            if value.startswith('#'):
                value = ''
        values[key] = value
    return values


def read_workspace_env(path: Path | str) -> dict[str, str]:
    """Read only the bounded literal shared private file; never mutate the shell.

    Callers must keep returned credentials local and out of logs/model content.
    Unknown/duplicate keys fail closed even when a different connector owns them.
    """
    return _parse(_read(Path(path), MAX_ENV_BYTES), allowed_keys=WORKSPACE_KEYS)


def _text(value: object, maximum: int, *, empty: bool = False) -> str:
    require(isinstance(value, str) and (empty or bool(value)) and len(value) <= maximum
            and not any(ord(char) < 32 or ord(char) == 127 for char in value),
            'Db2 settings require bounded literal text without control characters')
    return value


def _integer(value: object, maximum: int, message: str) -> int:
    require(isinstance(value, str) and re.fullmatch(r'[0-9]{1,6}', value), message)
    number = int(value)
    require(1 <= number <= maximum, message)
    return number


def _host(value: object) -> str:
    host = _text(value, 253)
    try:
        ipaddress.ip_address(host)
    except ValueError:
        require(all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label)
                    for label in host.rstrip('.').split('.')),
                'Db2 hostname must be a host name or IP address without URL or credentials')
    return host


def settings(env: Mapping[str, str] | None = None, env_file: Path | str | None = None, *, canonical: bool = False) -> Db2Settings:
    """Resolve settings; missing credentials/certificate are checked at connection.

    Explicit shell fields, including empty values, override file values. No
    environment changes, network calls or credential printing occur here. Explicit
    canonical selection requires an existing file and database/location equality;
    the legacy fixed-file contract remains compatible.
    """
    env = os.environ if env is None else env
    path = _path(Path(DEFAULT_ENV_FILE if env_file is None else env_file))
    values = _parse(_read(path, MAX_ENV_BYTES, missing_ok=not canonical), allowed_keys=WORKSPACE_KEYS)
    certificate_keys = ('DB2_SSL_SERVER_CERTIFICATE', 'DB2_SSL_CERT_LOCATION')
    # Alias ambiguity fails closed within either source. Explicit shell fields,
    # including an empty credential/certificate, override the entire alias pair.
    for source in (values, env):
        if all(key in source for key in certificate_keys):
            require(source[certificate_keys[0]] == source[certificate_keys[1]],
                    'Db2 certificate aliases must contain the same literal value')
    canonical = canonical or 'DB2_SSL_SERVER_CERTIFICATE' in values or 'DB2_SSL_SERVER_CERTIFICATE' in env
    if any(key in env for key in certificate_keys):
        for key in certificate_keys:
            values.pop(key, None)
    values.update({key: env[key] for key in KEYS if key in env})
    ssl_value = values.get('DB2_SSL_CONNECTION', '')
    require(isinstance(ssl_value, str) and ssl_value.lower() == 'true',
            'Db2 SSL must remain enabled')
    certificate = _text(values.get('DB2_SSL_SERVER_CERTIFICATE', values.get('DB2_SSL_CERT_LOCATION')), 1024)
    relative = Path(certificate)
    require(not relative.is_absolute() and not PureWindowsPath(certificate).drive
            and '\\' not in certificate and '..' not in relative.parts and relative.parts,
            'Db2 certificate path must stay relative to the private environment file')
    certificate_path = _path(path.parent / relative)
    row_limit = values.get('DB2_QUERY_ROW_LIMIT', '')
    location = _text(values.get('DB2_LOCATION_NAME'), 253)
    database = _text(values.get('DB2_DATABASE'), 253)
    require(not canonical or database == location,
            'The z/OS Db2 database must equal the configured location name')
    return Db2Settings(
        location=location,
        database=database,
        host=_host(values.get('DB2_HOSTNAME')),
        port=_integer(values.get('DB2_PORT'), 65535, 'Db2 port must be 1..65535'),
        ssl=True,
        certificate=certificate_path,
        username=_text(values.get('DB2_USERNAME', ''), 2048, empty=True),
        password=_text(values.get('DB2_PASSWORD', ''), 8192, empty=True),
        row_limit=MAX_ROWS if row_limit == '' else _integer(row_limit, MAX_ROWS, 'Db2 row limit must be 1..500000'),
    )


def _certificate(path: Path) -> None:
    validate_certificate(_read(path, MAX_CERT_BYTES))


def validate_certificate(content: bytes) -> None:
    """Validate the exact bounded CA bytes without network or credential access."""
    require(isinstance(content, bytes) and 0 < len(content) <= MAX_CERT_BYTES,
            'Supply an actual bounded Db2 CA certificate')
    try:
        if content.lstrip().startswith(b'-----BEGIN CERTIFICATE-----'):
            # Permit a PEM CA bundle, but reject keys and trailing unrelated data.
            blocks = re.findall(rb'-----BEGIN CERTIFICATE-----\s+[A-Za-z0-9+/=\s]+?-----END CERTIFICATE-----', content)
            require(bool(blocks) and not re.sub(
                rb'-----BEGIN CERTIFICATE-----\s+[A-Za-z0-9+/=\s]+?-----END CERTIFICATE-----', b'', content).strip(),
                'Db2 certificate must contain only valid PEM or DER certificates')
            tls.create_default_context(cadata=content.decode('ascii'))
        else:
            # DER must contain exactly one complete ASN.1 sequence.
            require(len(content) >= 4 and content[0] == 0x30,
                    'Db2 certificate must contain only valid PEM or DER certificates')
            first = content[1]
            if first < 128:
                offset, size = 2, first
            else:
                count = first & 127
                require(1 <= count <= 4 and len(content) >= 2 + count and content[2] != 0,
                        'Db2 certificate must contain only valid PEM or DER certificates')
                offset, size = 2 + count, int.from_bytes(content[2:2 + count], 'big')
                require(size >= 128, 'Db2 certificate must contain only valid PEM or DER certificates')
            require(offset + size == len(content),
                    'Db2 certificate must contain only valid PEM or DER certificates')
            tls.create_default_context(cadata=content)
    except (tls.SSLError, UnicodeError, ValueError):
        raise ValidationError('Supply an actual valid PEM or DER Db2 CA certificate') from None


def connection_string(env: Mapping[str, str] | None = None, env_file: Path | str | None = None, *, canonical: bool = False, driver: str = "IBM DB2 ODBC DRIVER") -> str:
    """Build an in-memory ODBC connection string. Never log or persist the result."""
    config = settings(env, env_file, canonical=canonical)
    require(bool(config.username) and bool(config.password),
            'Supply Db2 credentials through the private local environment')
    _certificate(config.certificate)
    driver = _text(driver, 253)
    values = {'DRIVER': driver, 'DATABASE': config.database,
              'HOSTNAME': config.host, 'PORT': config.port, 'PROTOCOL': 'TCPIP',
              'SECURITY': 'SSL', 'SSLServerCertificate': str(config.certificate),
              'SSLClientHostnameValidation': 'Basic', 'UID': config.username, 'PWD': config.password}
    return ';'.join(key + '={' + str(value).replace('}', '}}') + '}' for key, value in values.items()) + ';'
