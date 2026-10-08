"""Keep the public handoff small and its local links usable; never rewrite evidence."""
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
import hashlib
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workbench.domain import path_is_link
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DOCS = {'TECHNICAL_REFERENCE.md', 'executive-report.html', 'evidence.json'}
ENTRYPOINTS = ('START_HERE.md', 'AGENTS.md', 'CLAUDE.md', '.github/copilot-instructions.md', 'prompts/START_MODERNIZATION.md', 'knowledge/README.md')


def check_operator_reference(root=ROOT):
    """Reject stale navigation facts without reading a workspace or executing actions."""
    root = Path(root).resolve()
    issues = []
    def fail(message):
        issues.append('prompts/OPERATOR_GUIDE.json: ' + message)
    def safe_file(value):
        if not isinstance(value, str) or chr(92) in value:
            return None
        parts = PurePosixPath(value).parts
        if (not parts or PurePosixPath(value).is_absolute() or
                any(p in {'.', '..', '.git', '.implementation', '.migration', 'processes'} for p in parts) or
                PurePosixPath(value).as_posix() != value):
            return None
        path = root
        for part in parts:
            path /= part
            if path_is_link(path):
                return None
        return path if path.is_file() and path.resolve().is_relative_to(root) else None
    def digest(value):
        return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None
    def text(value, limit=2000):
        return isinstance(value, str) and bool(value.strip()) and len(value) <= limit
    def number(value):
        return type(value) is int
    path = safe_file('prompts/OPERATOR_GUIDE.json')
    if path is None:
        fail('reference is missing or unsafe'); return issues
    if path.stat().st_size > 32768:
        fail('reference exceeds 32,768 UTF-8 bytes'); return issues
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key ' + key)
            result[key] = value
        return result
    try:
        data = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_keys)
        if not isinstance(data, dict) or type(data.get('schema_version')) is not int or data.get('schema_version') != 1 or data.get('kind') != 'OPERATOR_GUIDE_REFERENCE':
            raise ValueError('unsupported reference schema')
        authority = {'operator_guide':'START_HERE.md', 'technical_contract':'docs/TECHNICAL_REFERENCE.md', 'workflow':'prompts/START_MODERNIZATION.md'}
        if data.get('authority') != authority:
            fail('authority must identify the existing guide, contract and workflow')
        use = data.get('use')
        if not isinstance(use, dict) or set(use) != {'read_order', 'invalidate', 'current_state', 'not_authorization'} or not all(text(v) for v in use.values()):
            fail('bounded usage and invalidation instructions are required')
        sources = data.get('sources')
        if not isinstance(sources, list) or not 3 <= len(sources) <= 64:
            raise ValueError('expected 3–64 source bindings')
        bound = {}
        for source in sources:
            if not isinstance(source, dict) or set(source) != {'path','sha256'}:
                raise ValueError('malformed source binding')
            name = source['path']
            source_path = safe_file(name)
            if source_path is None or name in bound or not digest(source['sha256']):
                raise ValueError('missing, unsafe, duplicate or invalid source binding')
            raw = source_path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != source['sha256']:
                fail('stale source binding: ' + name)
            bound[name] = len(raw.decode('utf-8').splitlines())
        if not set(authority.values()).issubset(bound):
            fail('all authority files must be hash-bound')
        job = data.get('job_aid')
        if not isinstance(job, dict) or job.get('filename') != 'mainframe-modernization-job-aid.html' or not digest(job.get('sha256')) or job.get('status') != 'REVIEW_DRAFT':
            raise ValueError('invalid contextual review-draft binding')
        steps = job.get('steps')
        if not isinstance(steps, list) or len(steps) != 46 or any(not isinstance(s, dict) or not number(s.get('id')) or not text(s.get('title'), 300) or not text(s.get('phase'), 300) for s in steps) or {s['id'] for s in steps} != set(range(1,47)):
            raise ValueError('expected exactly 46 distinct numbered review steps')
        topics = data.get('topics')
        if not isinstance(topics, list) or not 1 <= len(topics) <= 64:
            raise ValueError('expected 1–64 bounded topics')
        ids = set()
        for topic in topics:
            if not isinstance(topic, dict) or not text(topic.get('id'),80) or topic['id'] in ids or not text(topic.get('answer'),2000):
                raise ValueError('missing, duplicate or oversized topic')
            ids.add(topic['id'])
            matches = topic.get('match')
            if not isinstance(matches,list) or not 1 <= len(matches) <= 16 or not all(text(m,100) for m in matches):
                raise ValueError('invalid topic matching phrases')
            refs = topic.get('steps')
            if not isinstance(refs,list) or not refs or not all(number(n) and 1 <= n <= 46 for n in refs) or len(refs) != len(set(refs)):
                raise ValueError('invalid topic step references')
            spans = topic.get('read')
            if not isinstance(spans,list) or not 1 <= len(spans) <= 16:
                raise ValueError('invalid topic source spans')
            for span in spans:
                if not isinstance(span,dict) or span.get('path') not in bound:
                    raise ValueError('topic span is not hash-bound')
                lines = span.get('lines')
                if not isinstance(lines,list) or len(lines) != 2 or not all(number(n) for n in lines) or not 1 <= lines[0] <= lines[1] <= bound[span['path']] or lines[1]-lines[0] >= 80:
                    raise ValueError('topic span is out of bounds or exceeds 80 lines')
    except (ValueError, TypeError, KeyError, OSError, UnicodeError) as exc:
        fail(str(exc))
    return issues


def check(root=ROOT):
    root = Path(root).resolve()
    issues = []
    docs = root / 'docs'
    if not docs.is_dir() or path_is_link(docs):
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
        if not path.is_file() or path_is_link(path):
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
    issues.extend(check_operator_reference(root))
    return issues


if __name__ == '__main__':
    problems = check()
    for issue in problems: print(issue)
    if not problems: print('Handoff valid: one executive report, one technical reference, one evidence file; local links resolve.')
    raise SystemExit(2 if problems else 0)
