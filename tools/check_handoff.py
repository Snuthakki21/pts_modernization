"""Keep the public handoff small and its local links usable; never rewrite evidence."""
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DOCS = {'TECHNICAL_REFERENCE.md', 'executive-report.html', 'evidence.json'}
ENTRYPOINTS = ('START_HERE.md', 'AGENTS.md', 'CLAUDE.md', '.github/copilot-instructions.md', 'prompts/START_MODERNIZATION.md', 'knowledge/README.md')


def check(root=ROOT):
    root = Path(root).resolve()
    issues = []
    docs = root / 'docs'
    if not docs.is_dir() or docs.is_symlink():
        return ['docs must be a real directory']
    found = {p.name for p in docs.iterdir()}
    if found != DOCS:
        issues.append('docs must contain only: ' + ', '.join(sorted(DOCS)) + '; found: ' + ', '.join(sorted(found)))
    class Links(HTMLParser):
        def __init__(self):
            super().__init__(); self.links = []
        def handle_starttag(self, tag, attrs):
            if tag == 'a':
                self.links.extend(value for key, value in attrs if key == 'href' and value)
    skills=tuple(p.relative_to(root).as_posix() for p in (root/'.claude/skills').glob('*/SKILL.md'))
    for name in (*skills,*ENTRYPOINTS, 'docs/TECHNICAL_REFERENCE.md', 'docs/executive-report.html'):
        path = root / name
        if not path.is_file() or path.is_symlink():
            issues.append(name + ': required handoff file is missing or unsafe'); continue
        text = path.read_text(encoding='utf-8')
        if path.suffix == '.html':
            parser = Links(); parser.feed(text); links = parser.links
        else:
            links = re.findall(r'\[[^\]]+\]\(([^)]+)\)', text)
        for link in links:
            value = urlsplit(link)
            if value.scheme or value.netloc or not value.path:
                continue
            target = (path.parent / unquote(value.path)).resolve()
            if not target.is_relative_to(root) or not target.is_file():
                issues.append(name + ': broken or escaping local link ' + link)
    return issues


if __name__ == '__main__':
    problems = check()
    for issue in problems: print(issue)
    if not problems: print('Handoff valid: one executive report, one technical reference, one evidence file; local links resolve.')
    raise SystemExit(2 if problems else 0)
