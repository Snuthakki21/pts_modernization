"""Validate the documented workspace categories without moving frozen evidence."""
import argparse
import json
from pathlib import Path
import re
import unicodedata
from .domain import ValidationError, identity, require, safe_path
from .limits import MAX_SOURCE_ENTRIES, MAX_WORKSPACE_ENTRIES

ROOT_FILES = frozenset({
    '.env', '.env.example', '.gitignore', '.gitattributes', 'AGENTS.md', 'CLAUDE.md', 'README.md',
    'START_HERE.md', 'VALIDATION.md', 'requirements.lock', 'requirements.txt',
    'pyproject.toml', 'process-input.md', 'intake-template.xlsx',
    'mcp.json', '.mcp.json', 'zowe.config.json', 'zowe.config.user.json',
    'zowe.schema.json', 'zowe.config.schema.json', 'zowe.config.user.schema.json',
})
ROOT_DIRS = frozenset({
    'Endeavor', 'processes', 'shared', 'knowledge', '.migration',
    '.implementation', '.superpowers', 'release-private', '.git', '.venv',
    'node_modules', 'workbench', 'tests', 'tools', 'scripts', 'frontend',
    'docs', 'prompts', 'examples', '__pycache__', '.github',
    '.vscode', '.claude', 'Visio', 'certificates',
})
PROCESS_DIRS = frozenset({'input', 'analysis', 'review', 'synthetic', 'target', 'reports', 'tests'})
PRIVATE_DIRS = frozenset({'.migration', '.implementation', '.superpowers', 'release-private', '.git', '.venv', 'node_modules', '__pycache__'})


def output_path(root, process_id, relative):
    """Reject sibling escapes and outputs outside the process's named category."""
    base = safe_path(Path(root), 'processes/' + identity(process_id))
    path = safe_path(base, relative)
    parts = Path(relative).parts
    require(len(parts) >= 2 and parts[0] in PROCESS_DIRS,
            'Process outputs belong in input, analysis, review, synthetic, target, reports or tests')
    if parts[0] == 'input':
        require(parts[1] in {'process-input.md', 'sources', 'sme-return.xlsx', 'sme-return-inbox.xlsx'},
                'Input contains only the frozen manifest/sources and the designated SME return files')
        require(parts[1] == 'sources' and len(parts) >= 3 or len(parts) == 2 and parts[1] != 'sources',
                'Source exports belong under input/sources')
    if path.suffix.lower() in {'.py', '.sqlite', '.db'}:
        require(parts[0] in {'target', 'tests'} or parts[:2] == ('input', 'sources'),
                'Executable target/database output belongs under target or tests')
    if path.suffix.lower() == '.md':
        require(relative == 'input/process-input.md' or relative=='analysis/requirements.md' or len(parts)==3 and parts[:2]==('analysis','requirements') and re.fullmatch(r'[0-9a-f]{64}\.md',parts[2]) or parts[0] == 'input' and len(parts) >= 3 and parts[1] == 'sources',
                'Use structured analysis and coverage files; do not create Markdown per rule')
    return path


def validate_workspace(root):
    """Return placement errors; never read private file contents or follow symlinks."""
    root = Path(root)
    issues = []
    if root.is_symlink() or any(p.is_symlink() for p in root.absolute().parents):
        return ['Workspace root and its parents must not be symlinks']
    if not root.exists(): return issues
    if not root.is_dir(): return ['Workspace must be a directory']
    for index, child in enumerate(root.iterdir(), 1):
        if index > MAX_WORKSPACE_ENTRIES:
            issues.append('Workspace root exceeds the bounded directory-entry limit')
            return sorted(set(issues))
        if child.is_symlink(): issues.append(child.name + ': symlinks are not allowed'); continue
        if child.is_file() and child.name not in ROOT_FILES:
            issues.append(child.name + ': root file is not allowlisted')
        elif child.is_dir() and child.name not in ROOT_DIRS:
            issues.append(child.name + ': root directory is not allowlisted')
        elif not child.is_file() and not child.is_dir():
            issues.append(child.name + ': root entries must be regular files or directories')
    for category in ('Endeavor', 'processes', 'shared', 'knowledge', '.vscode', '.claude', 'Visio', 'certificates'):
        folder = root / category
        if not folder.is_dir() or folder.is_symlink(): continue
        identities={}
        limit = MAX_SOURCE_ENTRIES if category == 'Endeavor' else MAX_WORKSPACE_ENTRIES
        for index, path in enumerate(folder.rglob('*'), 1):
            if index > limit:
                issues.append(category + ': directory traversal exceeds the bounded entry limit')
                return sorted(set(issues))
            relative=path.relative_to(root).as_posix()
            key=unicodedata.normalize('NFC',relative).casefold()
            if key in identities and identities[key]!=relative:
                issues.append(relative + ': portable path identity collides with ' + identities[key])
            identities[key]=relative
            if path.is_symlink(): issues.append(relative + ': symlinks are not allowed')
            elif not path.is_file() and not path.is_dir():
                issues.append(relative + ': entries must be regular files or directories')
            else:
                try: safe_path(root,relative)
                except ValidationError as exc: issues.append(relative + ': ' + str(exc))
    processes = root / 'processes'
    if processes.is_dir() and not processes.is_symlink():
        for index, process in enumerate(processes.iterdir(), 1):
            if index > MAX_WORKSPACE_ENTRIES:
                issues.append('processes: directory traversal exceeds the bounded entry limit')
                break
            try: identity(process.name)
            except ValidationError: issues.append('processes/' + process.name + ': invalid process ID'); continue
            if not process.is_dir() or process.is_symlink():
                issues.append('processes/' + process.name + ': process must be a directory'); continue
            for index, child in enumerate(process.iterdir(), 1):
                if index > MAX_WORKSPACE_ENTRIES:
                    issues.append('processes/' + process.name + ': directory traversal exceeds the bounded entry limit')
                    break
                if child.name not in PROCESS_DIRS or not child.is_dir():
                    issues.append(child.relative_to(root).as_posix() + ': misplaced process output')
            for index, path in enumerate(process.rglob('*'), 1):
                if index > MAX_WORKSPACE_ENTRIES:
                    issues.append('processes/' + process.name + ': directory traversal exceeds the bounded entry limit')
                    break
                if path.is_dir() and not path.is_symlink():
                    parts=path.relative_to(process).parts
                    if len(parts)>1 and parts[0]=='input' and parts[1]!='sources':
                        issues.append(path.relative_to(root).as_posix() + ': input subdirectories belong under input/sources')
                if not path.is_file() or path.is_symlink(): continue
                try: output_path(root, process.name, path.relative_to(process).as_posix())
                except ValidationError as exc: issues.append(path.relative_to(root).as_posix() + ': ' + str(exc))
    shared = root / 'shared'
    if shared.is_dir() and not shared.is_symlink():
        for child in shared.iterdir():
            if child.name != 'target' or not child.is_dir(): issues.append(child.relative_to(root).as_posix() + ': shared versions belong in shared/target')
        target = shared / 'target'
        if target.is_dir() and not target.is_symlink():
            for child in target.iterdir():
                if child.name != 'python' or not child.is_dir():
                    issues.append(child.relative_to(root).as_posix() + ': shared target versions belong in target/python')
            python = target / 'python'
            if python.is_dir() and not python.is_symlink():
                for path in python.iterdir():
                    if not path.is_file() or not re.fullmatch(r'[0-9a-f]{64}\.py', path.name):
                        issues.append(path.relative_to(root).as_posix() + ': shared versions require a SHA-256 filename')
    knowledge = root / 'knowledge'
    if knowledge.is_dir() and not knowledge.is_symlink():
        for child in knowledge.iterdir():
            if child.name not in {'inbox', 'records.json', 'INDEX.md', 'mainframe-catalog.json', 'application-knowledge.json', 'inventory-baseline.json', 'input-locations.json', 'README.md'}:
                issues.append(child.relative_to(root).as_posix() + ': knowledge belongs in the standard/application catalog, canonical index/records or inbox')
            elif (child.name == 'inbox' and not child.is_dir()) or (child.name != 'inbox' and not child.is_file()):
                issues.append(child.relative_to(root).as_posix() + ': knowledge inbox must be a directory and canonical entries must be files')
    return sorted(set(issues))


def require_layout(root):
    issues = validate_workspace(root)
    require(not issues, 'Workspace layout invalid: ' + '; '.join(issues[:20]))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', '--root', default=str(Path.cwd()))
    args = parser.parse_args(argv)
    issues = validate_workspace(args.workspace)
    print(json.dumps({'valid': not issues, 'issues': issues}, indent=2))
    return 2 if issues else 0


if __name__ == '__main__': raise SystemExit(main())
