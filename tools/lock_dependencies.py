#!/usr/bin/env python3
"""Regenerate release hashes from official PyPI metadata; no unconstrained resolution.

Run with CPython 3.12 and its bundled pip. Changing these reviewed pins requires
re-running tests and downloading with pip --require-hashes on Windows, Linux and macOS.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import urllib.request

from pip._vendor.packaging.markers import Marker, default_environment
from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.utils import canonicalize_name
from pip._vendor.packaging.version import Version

PINS = {
    'aiofile': '3.12.3',
    'annotated-doc': '0.0.5',
    'annotated-types': '0.8.0',
    'anyio': '4.15.1',
    'attrs': '26.1.0',
    'authlib': '1.8.0',
    'beartype': '0.22.9',
    'cachetools': '7.2.1',
    'caio': '0.12.9',
    'cffi': '2.1.1',
    'click': '8.5.0',
    'cryptography': '50.0.2',
    'cyclopts': '5.1.1',
    'dnspython': '2.8.0',
    'docstring-parser': '0.18.0',
    'email-validator': '2.3.0',
    'et-xmlfile': '2.0.0',
    'exceptiongroup': '1.3.1',
    'fastapi': '0.142.2',
    'fastmcp': '4.0.11',
    'fastmcp-slim': '4.0.11',
    'griffelib': '2.3.0',
    'h11': '0.16.0',
    'httpcore2': '2.13.1',
    'httpx2': '2.13.1',
    'idna': '3.20',
    'jaraco-classes': '3.4.0',
    'jaraco-context': '6.1.2',
    'jaraco-functools': '4.6.0',
    'jeepney': '0.9.0',
    'joserfc': '1.7.5',
    'jsonref': '1.1.0',
    'jsonschema': '4.26.0',
    'jsonschema-path': '0.5.0',
    'jsonschema-specifications': '2025.9.1',
    'keyring': '25.7.0',
    'lxml': '6.1.3',
    'markdown-it-py': '4.2.0',
    'mcp': '2.3.0',
    'mcp-types': '2.3.0',
    'mdurl': '0.1.2',
    'more-itertools': '11.1.0',
    'openapi-pydantic': '0.6.0',
    'openpyxl': '3.1.5',
    'opentelemetry-api': '1.45.0',
    'packaging': '26.3',
    'pathable': '0.6.0',
    'pillow': '12.3.0',
    'platformdirs': '4.12.3',
    'py-key-value-aio': '0.4.6',
    'pycparser': '3.0',
    'pydantic': '2.13.5',
    'pydantic-core': '2.46.5',
    'pydantic-settings': '2.15.0',
    'pygments': '2.21.0',
    'pyjwt': '2.15.1',
    'pyperclip': '1.11.0',
    'python-docx': '1.2.0',
    'python-dotenv': '1.2.4',
    'python-multipart': '0.0.32',
    'python-pptx': '1.0.2',
    'pywin32': '312',
    'pywin32-ctypes': '0.2.3',
    'pyyaml': '6.0.3',
    'referencing': '0.37.0',
    'rich': '15.0.0',
    'rich-rst': '2.2.0',
    'rpds-py': '2026.9.1',
    'secretstorage': '3.5.0',
    'sse-starlette': '3.5.0',
    'starlette': '1.7.0',
    'truststore': '0.10.4',
    'typing-extensions': '4.16.0',
    'typing-inspection': '0.4.4',
    'uncalled-for': '0.4.0',
    'uvicorn': '0.54.0',
    'watchfiles': '1.3.0',
    'websockets': '17.2',
    'xlsxwriter': '3.2.9',
}


# The supported CPython platforms require distinct native credential backends.
MARKERS = {
    'jeepney': "sys_platform == 'linux'",
    'pywin32': "sys_platform == 'win32'",
    'pywin32-ctypes': "sys_platform == 'win32'",
    'secretstorage': "sys_platform == 'linux'",
}


def release_metadata(entry):
    name, version = entry
    url = f'https://pypi.org/pypi/{name}/{version}/json'
    request = urllib.request.Request(url, headers={'User-Agent': 'workbench-lock/1'})
    with urllib.request.urlopen(request, timeout=45) as response:
        result = json.load(response)
    if (canonicalize_name(result['info']['name']) != name or
            Version(result['info']['version']) != Version(version)):
        raise ValueError(f'Unexpected release identity for {name}')
    return name, result


def validate_dependencies(releases):
    """Check active pins and recursively requested extras for each workstation OS."""
    if set(releases) != set(PINS) or not set(MARKERS) <= set(PINS):
        raise ValueError('Release metadata and platform markers must match the reviewed pins')
    for system, platform, machine, os_name in [
            ('Linux', 'linux', 'x86_64', 'posix'),
            ('Windows', 'win32', 'AMD64', 'nt'),
            ('Darwin', 'darwin', 'arm64', 'posix'),
            ('Darwin', 'darwin', 'x86_64', 'posix')]:
        environment = dict(default_environment(), python_version='3.12',
                           python_full_version='3.12.0', platform_system=system,
                           sys_platform=platform, platform_machine=machine, os_name=os_name,
                           implementation_name='cpython', implementation_version='3.12.0',
                           platform_python_implementation='CPython', extra='')
        active = {name for name in PINS
                  if name not in MARKERS or Marker(MARKERS[name]).evaluate(environment)}
        # A lock entry installs its base requirements. Edges such as
        # fastmcp -> fastmcp-slim[client,server] also activate those extras,
        # whose own dependencies can request more extras further down the graph.
        requested = {name: {''} for name in active}
        pending = [(name, '') for name in sorted(active)]
        while pending:
            name, extra = pending.pop()
            release = releases[name]
            python_spec = release['info'].get('requires_python')
            if python_spec:
                from pip._vendor.packaging.specifiers import SpecifierSet
                if not SpecifierSet(python_spec).contains('3.12.0'):
                    raise ValueError(f'{name} does not support Python 3.12')
            selected_environment = dict(environment, extra=extra)
            for text in release['info'].get('requires_dist') or []:
                dependency = Requirement(text)
                if dependency.marker and not dependency.marker.evaluate(selected_environment):
                    continue
                dep_name = canonicalize_name(dependency.name)
                if (dependency.url or dep_name not in active or
                        not dependency.specifier.contains(PINS[dep_name])):
                    raise ValueError(f'{system}/{machine}: missing/incompatible pin for {name}: {text}')
                for selected_extra in dependency.extras:
                    selected_extra = canonicalize_name(selected_extra)
                    if selected_extra not in requested[dep_name]:
                        requested[dep_name].add(selected_extra)
                        pending.append((dep_name, selected_extra))


def render_lock(releases):
    lines = [
        '# CPython 3.12 Windows/Linux/macOS release lock; generated by tools/lock_dependencies.py.',
        '# SHA256 values are official https://pypi.org/pypi/<name>/<version>/json release digests.',
        '# All non-yanked wheels and sdists are listed; setup uses wheels only to avoid unpinned builds.',
        '# Refresh requires the full validation suite; hashes do not certify vulnerability status.',
        '# Optional live Db2 gateway: install pyodbc separately with your IBM driver.',
    ]
    for name, version in sorted(PINS.items()):
        release = releases[name]
        digests = set()
        for artifact in release['urls']:
            if artifact['yanked'] or artifact['packagetype'] not in ('bdist_wheel', 'sdist'):
                continue
            if not artifact['url'].startswith('https://files.pythonhosted.org/'):
                raise ValueError(f'Unexpected distribution host for {name}')
            digest = artifact['digests']['sha256']
            if not re.fullmatch('[0-9a-f]{64}', digest):
                raise ValueError(f'Invalid published SHA256 for {name}')
            digests.add(digest)
        if not digests:
            raise ValueError(f'No distributions for {name}')
        marker = '; ' + MARKERS[name] if name in MARKERS else ''
        lines.append(f'{name}=={version}{marker} \\')
        ordered = sorted(digests)
        lines.extend(f'    --hash=sha256:{digest}' + (' \\' if i < len(ordered)-1 else '')
                     for i, digest in enumerate(ordered))
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Verify existing lock against official release metadata')
    args = parser.parse_args()
    with ThreadPoolExecutor(max_workers=8) as pool:
        releases = dict(pool.map(release_metadata, PINS.items()))
    validate_dependencies(releases)
    contents = render_lock(releases)
    destination = Path(__file__).resolve().parents[1] / 'requirements.lock'
    if args.check:
        if destination.read_text(encoding='utf-8') != contents:
            raise SystemExit('Lock differs from official metadata; regenerate and revalidate')
        print(f'Verified all published SHA256 digests and transitive pins for {len(PINS)} releases')
    else:
        destination.write_text(contents, encoding='utf-8')
        print(f'Wrote {destination}: {len(PINS)} exact pins with published SHA256 digests')


if __name__ == '__main__':
    main()
