"""Validate the pinned instruction-only skill pack without network or execution.

Checks packaging, provenance structure, hashes, permissions and local links.
This is not native Claude activation, license advice or a semantic/DLP certificate.
"""
from pathlib import Path, PurePosixPath
import hashlib
import json
import re
import stat
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
ORIGINS = {
    'superpowers': 'obra/superpowers',
    'matt-pocock': 'mattpocock/skills',
    'ecc': 'affaan-m/ECC',
    'karpathy-guidelines': 'multica-ai/andrej-karpathy-skills',
    'anthropic-testing': 'anthropics/skills',
    'ponytail': 'DietrichGebert/ponytail',
    'ui-ux-pro-max': 'nextlevelbuilder/ui-ux-pro-max-skill',
    'caveman': 'JuliusBrussee/caveman',
    'agent-engineering': 'addyosmani/agent-skills',
    'taste': 'Leonxlnx/taste-skill',
    'understand-anything': 'Egonex-AI/Understand-Anything',
    'impeccable': 'pbakaus/impeccable',
    'headroom': 'headroomlabs-ai/headroom',
    'i-have-adhd': 'ayghri/i-have-adhd',
    'oh-my-claudecode': 'Yeachan-Heo/oh-my-claudecode',
}
RETAINED = {'mainframe-discovery', 'mainframe-semantics', 'mainframe-target', 'mainframe-assurance'}
EXCLUDED = {'executables', 'installers', 'MCP servers', 'proxies', 'hooks', 'background services', 'telemetry', 'automatic publishing'}
SHA = re.compile(r'[0-9a-f]{64}\Z')
COMMIT = re.compile(r'[0-9a-f]{40}\Z')


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def _canonical(value):
    return (isinstance(value, str) and 0 < len(value) <= 400 and
            not any(c in value for c in ('\\', ':', '\x00')) and
            not any(ord(c) < 32 or ord(c) == 127 for c in value) and
            not PurePosixPath(value).is_absolute() and
            PurePosixPath(value).as_posix() == value and
            all(p not in {'.', '..'} for p in value.split('/')))


def _local_link(root, origin, value):
    parsed = urlsplit(value)
    if parsed.scheme:
        return parsed.scheme == 'https' and bool(parsed.netloc)
    if parsed.netloc or parsed.query:
        return False
    raw = unquote(parsed.path)
    if not raw:
        return bool(parsed.fragment)
    if '\\' in raw or '\x00' in raw or Path(raw).is_absolute():
        return False
    candidate = origin.parent
    for part in raw.split('/'):
        if part == '..':
            candidate = candidate.parent
        elif part != '.':
            candidate /= part
        if not candidate.is_relative_to(root) or candidate.is_symlink():
            return False
    return candidate.is_file() and candidate.resolve().is_relative_to(root)


def check(root=ROOT):
    root = Path(root).absolute()
    issues = []
    manifest_path = root / '.claude/skill-pack.json'
    if any((root / p).is_symlink() for p in ('.claude', '.claude/skills', '.claude/skill-pack.json')):
        return {'passed': False, 'issues': ['skill pack root or manifest is a link']}
    try:
        if manifest_path.stat().st_size > 65536:
            raise ValueError('manifest exceeds bounded size')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'), object_pairs_hook=_unique)
        if not isinstance(manifest, dict) or type(manifest.get('schema_version')) is not int or manifest['schema_version'] != 1 or manifest.get('kind') != 'WORKBENCH_TEXT_ONLY_SKILL_PACK':
            raise ValueError('invalid manifest schema')
        expected_manifest_fields = {'schema_version', 'kind', 'index_url', 'mode', 'runtime_installed', 'permission_grants', 'load_policy', 'official_skill_contract', 'retained_skills', 'packages'}
        if set(manifest) != expected_manifest_fields:
            issues.append('unknown manifest field or missing required field')
        if manifest.get('mode') != 'curated_markdown_instructions' or manifest.get('runtime_installed') is not False:
            issues.append('runtime installation is forbidden')
        if manifest.get('permission_grants') != []:
            issues.append('skill permissions must be empty')
        if set(manifest.get('retained_skills', [])) != RETAINED:
            issues.append('retained skill set must preserve four mainframe skills')
        if manifest.get('index_url') != 'https://github.com/quemsah/awesome-claude-plugins' or manifest.get('official_skill_contract') != 'https://code.claude.com/docs/en/skills':
            issues.append('public index and official skill contract must be explicit')
        if not isinstance(manifest.get('load_policy'), str) or not 1 <= len(manifest['load_policy']) <= 1000:
            issues.append('bounded load policy is required')
        packages = manifest.get('packages')
        if not isinstance(packages, list) or len(packages) > 30:
            raise ValueError('bounded package list is required')
        names = [p.get('name') for p in packages if isinstance(p, dict)]
        if len(names) != len(set(names)):
            issues.append('duplicate package')
        if set(names) != set(ORIGINS) or len(packages) != 15:
            issues.append('requested package set must contain exactly 15 origins')
        skills_root = root / '.claude/skills'
        directories = set()
        for item in skills_root.iterdir():
            if item.is_symlink():
                issues.append('skill directory is a link'); continue
            if not item.is_dir():
                issues.append('unexpected file at skill directory root'); continue
            directories.add(item.name)
        if directories != set(ORIGINS) | RETAINED:
            issues.append('skill directory set must be the 15 packages and four retained skills')
        for name in RETAINED:
            path = skills_root / name / 'SKILL.md'
            if not path.is_file() or path.is_symlink():
                issues.append('retained skill missing or link: ' + name)
            directory = skills_root / name
            if directory.is_dir() and not directory.is_symlink():
                for item in directory.iterdir():
                    if item.name != 'SKILL.md' or item.is_symlink() or not item.is_file() or item.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
                        issues.append('retained skill payload must remain instruction-only: ' + name)
        count = 0; total_bytes = 0; descriptions = 0; instruction_bytes = 0
        for package in packages:
            if not isinstance(package, dict) or package.get('name') not in ORIGINS:
                issues.append('invalid package record'); continue
            name = package['name']; prefix = '.claude/skills/' + name + '/'
            if (skills_root / name).is_symlink():
                issues.append(name + ': package directory is a link'); continue
            if package.get('requested_origin') != ORIGINS[name]:
                issues.append(name + ': incorrect origin')
            pin = package.get('upstream_commit')
            if not isinstance(pin, str) or not COMMIT.fullmatch(pin):
                issues.append(name + ': immutable commit is required')
            source = package.get('source', {})
            if not isinstance(source, dict):
                issues.append(name + ': source provenance missing'); source = {}
            source_path = source.get('path')
            if not _canonical(source_path):
                issues.append(name + ': unsafe source path')
            expected_url = f'https://github.com/{ORIGINS[name]}/blob/{pin}/{source_path}'
            if source.get('url') != expected_url:
                issues.append(name + ': pinned source URL mismatch')
            if not isinstance(source.get('sha256'), str) or not SHA.fullmatch(source['sha256']):
                issues.append(name + ': original source hash missing')
            adapter = name in {'headroom', 'karpathy-guidelines'}
            if package.get('mode') != ('independently_authored_adapter' if adapter else 'adapted_upstream_subset'):
                issues.append(name + ': adapter/subset mode mismatch')
            if name == 'headroom' and (source_path != 'README.md' or not isinstance(package.get('qualification'), str)):
                issues.append(name + ': no-upstream-skill adapter qualification required')
            excluded = package.get('excluded')
            if not isinstance(excluded, list) or set(excluded) != EXCLUDED or len(excluded) != len(EXCLUDED):
                issues.append(name + ': runtime exclusions must be explicit')
            license_info = package.get('license', {})
            if not isinstance(license_info, dict):
                issues.append(name + ': license metadata required'); license_info = {}
            if name == 'karpathy-guidelines':
                if license_info.get('spdx') != 'NOASSERTION' or license_info.get('redistributed_upstream_text') is not False or license_info.get('source_path') is not None or license_info.get('sha256') is not None or not isinstance(license_info.get('qualification'), str):
                    issues.append(name + ': unlicensed upstream text cannot be redistributed')
            elif (license_info.get('spdx') not in {'MIT', 'Apache-2.0'} or not _canonical(license_info.get('source_path')) or not isinstance(license_info.get('sha256'), str) or not SHA.fullmatch(license_info['sha256'])):
                issues.append(name + ': applicable license provenance required')
            records = package.get('files')
            if not isinstance(records, list) or not 1 <= len(records) <= 2:
                issues.append(name + ': bounded installed file list required'); continue
            registered = set(); package_bytes = 0
            for record in records:
                if not isinstance(record, dict):
                    issues.append(name + ': malformed file record'); continue
                path_text = record.get('path')
                if not _canonical(path_text) or path_text not in {prefix + 'SKILL.md', prefix + 'LICENSE.md'}:
                    issues.append(name + ': unsafe file path'); continue
                if path_text in registered:
                    issues.append(name + ': duplicate file record')
                registered.add(path_text); path = root / path_text
                if path.is_symlink():
                    issues.append(name + ': installed file is a link'); continue
                if not path.is_file():
                    issues.append(name + ': registered file missing'); continue
                if path.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
                    issues.append(name + ': executable file forbidden')
                raw = path.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
                if record.get('sha256') != digest or type(record.get('bytes')) is not int or record['bytes'] != len(raw):
                    issues.append(name + ': installed hash/size mismatch')
                package_bytes += len(raw); count += 1
                if path.name == 'LICENSE.md' and digest != license_info.get('sha256'):
                    issues.append(name + ': license hash/size mismatch')
                text = raw.decode('utf-8')
                if path.name != 'SKILL.md':
                    continue
                instruction_bytes += len(raw)
                if len(raw) > 8192:
                    issues.append(name + ': instruction text exceeds 8192 bytes')
                match = re.match(r'\A---\n(.*?)\n---\n', text, re.S)
                fields = {}
                if match:
                    for line in match.group(1).splitlines():
                        if ': ' not in line:
                            issues.append(name + ': unsupported frontmatter'); continue
                        key, value = line.split(': ', 1)
                        if key in fields:
                            issues.append(name + ': duplicate frontmatter')
                        fields[key] = value
                expected_fields = {'name', 'description'} | ({'disable-model-invocation'} if name in {'caveman', 'i-have-adhd'} else set())
                if set(fields) != expected_fields or fields.get('name') != name or ('disable-model-invocation' in fields and fields['disable-model-invocation'] != 'true'):
                    issues.append(name + ': frontmatter must not grant tools, permissions or runtime state')
                description = fields.get('description', '')
                if not 1 <= len(description) <= 256:
                    issues.append(name + ': description must be bounded to 256 characters')
                descriptions += len(description)
                for value in re.findall(r'\[[^\]]*\]\(([^)]+)\)', text):
                    if not _local_link(root, path, value):
                        issues.append(name + ': broken or unsafe local reference')
                if 'adapted instruction-only skill' not in text or 'grants no tools' not in text:
                    issues.append(name + ': explicit instruction-only boundary required')
            expected_files = {prefix + 'SKILL.md'} | ({prefix + 'LICENSE.md'} if name != 'karpathy-guidelines' else set())
            if registered != expected_files or package.get('file_count') != len(records) or type(package.get('installed_bytes')) is not int or package['installed_bytes'] != package_bytes:
                issues.append(name + ': registered cardinality/bytes mismatch')
            directory = skills_root / name
            if directory.is_dir() and not directory.is_symlink():
                for path in directory.iterdir():
                    if path.is_symlink():
                        issues.append(name + ': link payload forbidden')
                    elif path.is_dir():
                        issues.append(name + ': unexpected directory')
                    elif path.suffix != '.md' or path.relative_to(root).as_posix() not in registered:
                        issues.append(name + ': unregistered or non-Markdown payload')
            total_bytes += package_bytes
        if descriptions > 4096 or instruction_bytes > 65536 or total_bytes > 200000:
            issues.append('aggregate instruction/description/byte budget exceeded')
        return {'passed': not issues, 'issues': issues, 'package_count': len(packages),
                'skill_count': len(directories), 'file_count': count,
                'installed_bytes': total_bytes, 'instruction_bytes': instruction_bytes,
                'description_characters': descriptions,
                'scope': 'Offline text-only packaging and provenance validation; no runtime, activation, semantic, privacy or license certification'}
    except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
        return {'passed': False, 'issues': ['skill pack inspection failed: ' + str(exc)]}


if __name__ == '__main__':
    result = check()
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 1)
