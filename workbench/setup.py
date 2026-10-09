"""Deterministic operator preparation; no source, credential or network access."""
from .domain import path_is_link
import os
from pathlib import Path
import re
import shutil
import threading

from .domain import ValidationError, atomic_bytes, atomic_json, decode, encode, require, safe_path, sha
from .limits import MAX_SOURCE_BYTES, MAX_SOURCE_FILE_BYTES, MAX_SOURCE_FILES, MAX_SOURCE_LINES, MAX_UI_SOURCE_BYTES

MAX_SETUP_BYTES = 4096
_LOCK = threading.RLock()
_QUESTIONS = (
    ('source', 'Source export', 'How will you supply the complete read-only source export?',
     (('local_endeavor', 'Local Endeavor folder'), ('upload', 'Upload source files'), ('needs_setup', 'Help preparing the export'))),
    ('manifest', 'Process intake', 'Is the process manifest ready with ordered jobs and steps?',
     (('ready', 'Manifest ready'), ('needs_setup', 'Prepare the manifest'))),
    ('zowe', 'Read-only Zowe', 'Does Claude Code need approved read-only Zowe retrieval for this process?',
     (('not_needed', 'Not needed'), ('configured', 'Configured locally'), ('needs_setup', 'Help configuring Zowe'))),
    ('db2', 'Read-only Db2', 'Does Claude Code need approved read-only Db2 catalog retrieval for this process?',
     (('not_needed', 'Not needed'), ('configured', 'Configured locally'), ('needs_setup', 'Help configuring Db2'))),
    ('llm', 'Analysis workflow', 'Use Claude Code for approved retrieval, local analysis, development and tests, or choose a deterministic/provider alternative?',
     (('copilot_chat', 'Claude Code end-to-end (Recommended)'), ('disabled', 'Deterministic analysis'), ('opt_in', 'Legacy approved provider suggestions'))),
    ('reviewer', 'Human reviewer', 'Is a real human reviewer available for the single SME workbook?',
     (('available', 'Reviewer available'), ('needs_setup', 'Arrange a reviewer'))),
)
_VALUES = {key: {value for value, _ in choices} for key, _, _, choices in _QUESTIONS}


def deterministic_metrics():
    return {'mode':'deterministic', 'llm_requests':0, 'input_tokens':0,
            'output_tokens':0, 'network_requests':0}


def _validate_answers(answers, *, partial):
    require(isinstance(answers, dict) and (bool(answers) if partial else set(answers) == set(_VALUES)),
            'Setup answers must contain the supported questions')
    require(set(answers) <= set(_VALUES), 'Unknown setup question; credentials and free text are not accepted')
    for key, value in answers.items():
        require(value is None or isinstance(value, str) and value in _VALUES[key],
                'Choose a listed setup option or null to reset it')
    return dict(answers)


def _state_path(workspace):
    root = Path(workspace).absolute()
    require(root.is_dir(), 'Setup requires an existing workspace directory')
    return safe_path(root, '.migration/setup.json')


def _load(path):
    if not path.exists(): return dict.fromkeys(_VALUES)
    require(path.is_file() and path.stat().st_size <= MAX_SETUP_BYTES,
            'Setup state must be a regular JSON file of at most 4096 bytes')
    with path.open('rb') as handle: data = handle.read(MAX_SETUP_BYTES + 1)
    document = decode(data, MAX_SETUP_BYTES)
    require(isinstance(document, dict) and set(document) == {'version', 'answers'}
            and type(document['version']) is int and document['version'] == 1,
            'Unsupported setup state document; preserve it and correct the local setup state')
    return _validate_answers(document['answers'], partial=False)


def _configuration(root, env):
    from .connectors import endpoint, ZoweReader
    from .provider import StructuredProvider
    try: source = safe_path(root, 'Endeavor').is_dir()
    except ValidationError: source = False
    zowe = db2 = llm = False
    if env.get('WB_ZOWE_PROFILE'):
        try:
            ZoweReader(env['WB_ZOWE_PROFILE'], env.get('WB_ZOWE_ZOSMF_PROFILE'))
            hint = env.get('WB_DATASET_HINT', '*')
            require(isinstance(hint, str) and re.fullmatch(r'[A-Za-z0-9@$#.*()_-]{1,150}', hint)
                    and not hint.startswith('-'), 'Invalid dataset hint')
            zowe = bool(shutil.which('zowe', path=env.get('PATH', os.defpath)))
        except (ValidationError, OSError): pass
    if env.get('WB_DB2_MCP_URL'):
        try: endpoint(env['WB_DB2_MCP_URL']); db2 = True
        except ValidationError: pass
    # Text-first setup is explicit to this workspace, never a home/cwd scan.
    # These are local preparation facts, not authentication or read-access proof.
    if safe_path(root,'.env').is_file():
        try:
            from .zowe_setup import environment_profiles
            environment_profiles(root)
            zowe=bool(shutil.which('zowe',path=env.get('PATH',os.defpath)))
        except (ValidationError,OSError,UnicodeError):pass
        try:
            from .db2_setup import inspect_stdio_binding
            from .db2_env import settings as db2_settings, _certificate
            inspect_stdio_binding(root)
            private=db2_settings({},safe_path(root,'.env'),canonical=True)
            _certificate(private.certificate)
            db2=True
        except (ValidationError,OSError,UnicodeError):pass
    if env.get('WB_LLM_URL'):
        try:
            # Validate public configuration syntax without reading the private token.
            StructuredProvider(env['WB_LLM_URL'], env.get('WB_LLM_MODEL'), '')
            require(env.get('WB_ALLOW_SOURCE_EGRESS', 'false') in ('true', 'false'), 'Invalid egress value')
            llm = True
        except ValidationError: pass
    return {'local_source_export':source, 'zowe_configured':zowe, 'db2_configured':db2,
            'llm_configured':llm, 'source_egress_approved':env.get('WB_ALLOW_SOURCE_EGRESS') == 'true'}


def _view(root, answers, env):
    config = _configuration(root, env)
    # Keep the version-1 saved choice key; only its active workflow changes.
    config['assistant_mode'] = {'disabled': 'deterministic', 'opt_in': 'opt_in'}.get(answers['llm'], 'claude_files')
    actions = {
        'source':f'Choose the complete local Endeavor export (up to {MAX_SOURCE_FILES:,} files, {MAX_SOURCE_FILE_BYTES // (1024 * 1024)} MiB per file, {MAX_SOURCE_BYTES // (1024 * 1024)} MiB combined and {MAX_SOURCE_LINES:,} physical lines) or upload up to {MAX_UI_SOURCE_BYTES // (1024 * 1024)} MiB in the browser. Keep larger exports in local Endeavor; preserve every original file and never execute the source.',
        'manifest':'Download the intake template, supply the real process ID and ordered jobs/steps, then mark the manifest ready. Setup does not invent process facts.',
        'zowe':'Copy .env.example to the private workspace .env and fill the ZOWE values locally. Put the approved PEM CA at certificates/ZOWE-CA.pem. Run tools/setup_zowe.py --workspace WORKSPACE --from-env --env-file WORKSPACE/.env to prepare clean profiles/schema; no existing profile is needed. For Explorer run zowe config secure from the workspace and enter credentials in its local prompts. The .env alone does not sign Explorer in. Existing different files are preserved; WEBELX and Tran Repository availability and input readiness stay Unknown.',
        'db2':'Fill the eight DB2 values in the same private workspace .env. Database must equal DDF location. Put the approved CA at certificates/DB2-CA.cert, outside .migration, and keep TLS enabled. Run python -m workbench.db2_setup --workspace WORKSPACE --env-file WORKSPACE/.env, then scripts/Start-Claude.ps1 -Workspace WORKSPACE. Claude owns the local read-only Db2 stdio MCP server; no transport token or separate server terminal is needed. Credentials remain local and configuration is not read-access proof.',
        'llm':'Claude Code retrieves requested mainframe source with read-only Zowe CLI and Db2 evidence through approved MCP, then owns local lineage analysis, development, testing and review. Requested exports go into exact hash-bound local inboxes. Return to Claude and say Continue; the existing Coordinator validates the files before resuming. Use python -m workbench.runner agent PROCESS_ID --workspace WORKSPACE for local task state. No model endpoint or API token is needed by this workflow. Actual credits remain Unknown without receipts. One authentic SME return and deterministic verification are still required.',
        'reviewer':'Arrange a real human reviewer for the one SME workbook. Availability is preparation only; the actual returned workbook and reviewer attribution remain required.',
    }
    complete = {
        'source':answers['source'] == 'upload' or answers['source'] == 'local_endeavor' and config['local_source_export'],
        'manifest':answers['manifest'] == 'ready',
        'zowe':answers['zowe'] == 'not_needed' and not env.get('WB_ZOWE_PROFILE') or answers['zowe'] == 'configured' and config['zowe_configured'],
        'db2':answers['db2'] == 'not_needed' and not env.get('WB_DB2_MCP_URL') or answers['db2'] == 'configured' and config['db2_configured'],
        'llm':answers['llm'] == 'copilot_chat' or answers['llm'] == 'disabled' and not env.get('WB_LLM_URL') or answers['llm'] == 'opt_in' and config['llm_configured'] and config['source_egress_approved'],
        'reviewer':answers['reviewer'] == 'available',
    }
    if answers['llm'] == 'disabled' and env.get('WB_LLM_URL'):
        actions['llm'] = 'Remove WB_LLM_URL from the launch environment and restart for deterministic analysis. Saving this answer does not change the running provider configuration or authorize source transfer.'
    elif answers['llm'] == 'opt_in':
        actions['llm'] = 'For the legacy provider, configure WB_LLM_URL and WB_LLM_MODEL and explicitly set WB_ALLOW_SOURCE_EGRESS=true in the launch environment, then restart. Use only approved source excerpts and keep tokens outside this questionnaire.'
    for key, variable in (('zowe', 'WB_ZOWE_PROFILE'), ('db2', 'WB_DB2_MCP_URL')):
        if answers[key] == 'not_needed' and env.get(variable):
            actions[key] = 'Remove ' + variable + ' from the launch environment and restart to omit this optional read-only discovery. Saving this answer does not change runtime configuration.'
    questions = [{'id':key, 'title':title, 'prompt':prompt,
                  'options':[{'value':value, 'label':label} for value, label in choices],
                  'answer':answers[key], 'status':'ANSWERED' if complete[key] else 'UNANSWERED' if answers[key] is None else 'NEEDS_ACTION',
                  'action':actions[key]} for key, title, prompt, choices in _QUESTIONS]
    pending = [q for q in questions if q['status'] != 'ANSWERED']
    return {'version':1, 'answers':dict(answers), 'questions':questions,
            'actions':[{key:q[key] for key in ('id', 'title', 'action')} for q in pending],
            'next_step':pending[0]['id'] if pending else None,
            'readiness':{'status':'NEEDS_SETUP' if pending else 'READY_FOR_INTAKE',
                         'answered':sum(value is not None for value in answers.values()), 'total':len(_QUESTIONS),
                         'remaining':[q['id'] for q in pending], 'connectivity_verified':False,
                         'source_verified':False, 'conversion_verified':False},
            'configuration':config, 'metrics':deterministic_metrics(),
            'scope':'Operator preparation only. Source validation, live connectivity, actual human review and conversion verification remain separate gates. This questionnaire performs no network or LLM calls.'}


def inspect_setup(workspace, *, environ=None):
    """Read bounded nonsecret preferences and local configuration; never contact a service."""
    with _LOCK:
        path = _state_path(workspace)
        return _view(path.parent.parent, _load(path), dict(os.environ if environ is None else environ))


def save_setup(workspace, answers, *, environ=None):
    """Atomically merge a bounded enum patch, preserving all workflow and source evidence."""
    update = _validate_answers(answers, partial=True)
    with _LOCK:
        path = _state_path(workspace)
        current = _load(path)
        current.update(update)
        result = _view(path.parent.parent, current, dict(os.environ if environ is None else environ))
        atomic_json(path, {'version':1, 'answers':current})
        return result

# Keep the historical questionnaire contract intact. These actual workstation
# values are a separate, ignored local document and never carry credentials.
MAX_WORKSTATION_BYTES = 16384
_WORKSTATION_FIELDS = ('source_mode', 'source_folder', 'process_notes', 'wedlx_folder',
                       'tran_repository_folder', 'zowe_profile', 'zowe_zosmf_profile',
                       'db2_metadata_url')
_CONNECTION_FIELDS = {'zowe_profile': 'WB_ZOWE_PROFILE',
                      'zowe_zosmf_profile': 'WB_ZOWE_ZOSMF_PROFILE',
                      'db2_metadata_url': 'WB_DB2_MCP_URL'}


def _workstation_path(workspace):
    root=_state_path(workspace).parent.parent
    return safe_path(root,'.migration/workstation.json')


def _local_path(root, value, field, *, check_links=True):
    require(isinstance(value, str) and 0 < len(value) <= 2048 and value == value.strip()
            and not any(ord(c) < 32 or ord(c) == 127 for c in value),
            field + ': supply a local path without control characters')
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    path = path.absolute()
    if check_links:
        require(not any(path_is_link(p) for p in (path, *path.parents)),
                field + ': use the direct path rather than a symlink')
        return str(path.resolve())
    return str(path)


def _validate_workstation(root, settings, *, partial=False, local_safety=True):
    from .connectors import endpoint, ZoweReader
    from urllib.parse import urlsplit
    require(isinstance(settings, dict) and bool(settings) and set(settings) <= set(_WORKSTATION_FIELDS)
            and (partial or set(settings) == set(_WORKSTATION_FIELDS)),
            'Supply only the supported nonsecret workstation settings')
    result = dict(settings)
    for field, value in result.items():
        if field == 'source_mode':
            require(value in ('folder', 'upload') and isinstance(value, str),
                    'source_mode: choose folder or upload')
        elif value is not None:
            require(isinstance(value, str), field + ': supply text or null to clear it')
            if field in _CONNECTION_FIELDS:
                if field == 'db2_metadata_url':
                    endpoint(value)
                    require(not urlsplit(value).query,
                            'db2_metadata_url: omit URL queries; keep authentication in the approved secure store')
                else:
                    require(not value.startswith('-'),field + ': choose a profile alias rather than a command option')
                    ZoweReader(value)
            else:
                result[field] = _local_path(root, value, field, check_links=local_safety)
    return result


def load_workstation_settings(workspace):
    """Return typed local defaults, without reading source/notes or contacting a host."""
    path = _workstation_path(workspace)
    root = path.parent.parent
    defaults = dict.fromkeys(_WORKSTATION_FIELDS)
    defaults['source_mode'] = 'folder' if safe_path(root, 'Endeavor').is_dir() else 'upload'
    if defaults['source_mode'] == 'folder':
        defaults['source_folder'] = str(root / 'Endeavor')
    if not path.exists():
        return defaults
    require(path.is_file() and path.stat().st_size <= MAX_WORKSTATION_BYTES,
            'Workstation settings must be a regular bounded JSON file')
    with path.open('rb') as stream:
        document = decode(stream.read(MAX_WORKSTATION_BYTES + 1), MAX_WORKSTATION_BYTES)
    require(isinstance(document, dict) and set(document) == {'version', 'settings'}
            and type(document['version']) is int and document['version'] == 1,
            'Unsupported workstation settings; preserve the file and correct its format')
    result = _validate_workstation(root, document['settings'], local_safety=False)
    require(result['source_mode'] != 'upload' or result['source_folder'] is None,
            'Upload setup must not retain a source folder')
    return result


def workstation_environment(workspace, environ=None):
    """Overlay explicit saved nonsecret choices without mutating process environment."""
    env = dict(os.environ if environ is None else environ)
    if _workstation_path(workspace).exists():
        settings = load_workstation_settings(workspace)
        for field, variable in _CONNECTION_FIELDS.items():
            if settings[field] is None:
                env.pop(variable, None)
            else:
                env[variable] = settings[field]
    return env


def _workstation_view(root, settings, *, saved):
    checks = []
    def add(field, status, message, action=''):
        checks.append({'id': field, 'status': status, 'message': message, 'action': action})
    if settings['source_mode'] == 'folder':
        folder=Path(settings['source_folder']) if settings['source_folder'] else None
        present=bool(folder and not any(path_is_link(p) for p in (folder,*folder.parents)) and folder.is_dir())
        add('source_folder', 'READY' if present else 'BLOCKED',
            'Local export folder is available; its content is checked at intake.' if present else 'Select an existing source export folder.',
            '' if present else 'Enter the direct path to the complete local Endeavor export.')
    else:
        add('source_folder', 'READY', 'Upload source files when starting each process.')
    for field, label in (('process_notes', 'Process notes'), ('wedlx_folder', 'WEBELX folder'),
                         ('tran_repository_folder', 'Tran Repository folder')):
        value = settings[field]
        if value is None:
            add(field, 'NOT_CONFIGURED', label + ' is optional.')
        else:
            path=Path(value)
            safe=not any(path_is_link(p) for p in (path,*path.parents))
            available=safe and (path.is_file() if field == 'process_notes' else path.is_dir())
            add(field, 'READY' if available else 'BLOCKED',
                label + ' is available; business readiness remains unverified.' if available else label + ' is no longer available.',
                '' if available else 'Correct this path or clear the optional value and save.')
    require(settings['zowe_profile'] is not None or settings['zowe_zosmf_profile'] is None,
            'zowe_zosmf_profile: also select the approved base profile')
    for field, label in (('zowe_profile', 'Zowe profile'), ('db2_metadata_url', 'Db2 metadata endpoint')):
        add(field, 'UNVERIFIED' if settings[field] else 'NOT_CONFIGURED',
            label + ' is saved for approved Claude Code retrieval; no connection was attempted.' if settings[field]
            else label + ' is optional; use existing approved Claude Code connections when needed.')
    remaining = [c['id'] for c in checks if c['status'] == 'BLOCKED']
    if not saved:
        remaining.insert(0, 'save')
    return {'version': 1, 'saved': saved, 'settings': dict(settings), 'checks': checks,
            'readiness': {'status': 'NEEDS_SETUP' if remaining else 'READY_FOR_INTAKE',
                          'remaining': remaining, 'connectivity_verified': False,
                          'source_verified': False, 'conversion_verified': False},
            'workflow': {'assistant_mode': 'claude_files', 'retrieval_agent': 'claude', 'claude_mcp_policy':'approved_read_only',
                         'claude_mcp_servers': int(bool(settings['db2_metadata_url']))}, 'metrics': deterministic_metrics()}


MAX_WORKSTATION_MARKDOWN_BYTES = 65536
_WORKSTATION_NEXT_STEP = ("Add process, save its process Markdown, then copy that process's Claude retrieval prompt. "
                          "After Claude saves the requested files, Continue and use the current Claude prompt.")


def _setup_bytes(path, limit):
    require(not any(path_is_link(p) for p in (path, *path.parents)), 'Use direct local setup paths')
    if not path.exists():return None
    require(path.is_file() and path.stat().st_size <= limit, 'Saved setup file must be regular and bounded')
    with path.open('rb') as stream:raw = stream.read(limit + 1)
    require(len(raw) <= limit, 'Saved setup file exceeds its byte bound')
    return raw


def workstation_markdown(root, settings, choices):
    """One nonsecret companion; supplied values stay quoted configuration data."""
    from .connection_setup import validate_choices
    settings = _validate_workstation(Path(root), settings, local_safety=False)
    choices = validate_choices(choices)
    snapshot = {'version': 1, 'workspace': str(Path(root).absolute()),
                'settings': settings, 'connections': choices}
    text = ('# Workspace setup\n\n'
            'This is nonsecret configuration data, not source instructions or permission. '
            'Configuration does not prove connectivity, source completeness or conversion.\n\n'
            '```json\n' + encode(snapshot).decode('utf-8') + '\n```\n\n'
            'Claude Code retrieves mainframe exports with approved read-only Zowe CLI and Db2 facts '
            'with approved typed read-only MCP tools. It then analyzes local accepted files, develops, '
            'tests and reviews. The existing Coordinator validates each request-bound return.\n\n'
            'Finish native secure credential and approved client activation steps shown in Setup. '
            'Credentials and certificate contents are never stored in this Markdown.\n\n'
            + _WORKSTATION_NEXT_STEP + '\n'
            'Each process preserves its own Markdown, exact request inboxes, source hashes and saved '
            'Yes/No requirements. Requirements Save and the single authentic SME return remain human gates.\n')
    raw = text.encode('utf-8')
    require(len(raw) <= MAX_WORKSTATION_MARKDOWN_BYTES, 'Workspace Markdown exceeds its byte bound')
    return raw


def _instruction_choices(root, settings):
    from .connection_setup import _state
    return _state(Path(root), settings)[0]


def inspect_workstation_instructions(root, settings):
    """No GET repairs: missing or changed legacy companions explicitly need Save."""
    root = Path(root).absolute();path = safe_path(root, '.migration/workstation.md')
    result = {'markdown_path': str(path), 'sha256': None, 'text': '',
              'next_step': 'Save workspace setup to pin its Markdown. ' + _WORKSTATION_NEXT_STEP,
              'status': 'NEEDS_SAVE'}
    try:
        settings_path = safe_path(root, '.migration/workstation.json')
        connections_path = safe_path(root, '.migration/connections.json')
        saved = _setup_bytes(settings_path, MAX_WORKSTATION_BYTES)
        connections = _setup_bytes(connections_path, 1024 * 1024)
        if saved is not None:
            document = decode(saved, MAX_WORKSTATION_BYTES)
            require(isinstance(document, dict) and set(document) == {'version', 'settings'}
                    and type(document['version']) is int and document['version'] == 1,
                    'Unsupported saved workstation settings')
            actual = _validate_workstation(root, document['settings'], local_safety=False)
            require(actual['source_mode'] != 'upload' or actual['source_folder'] is None,
                    'Upload setup must not retain a source folder')
            supplied = _validate_workstation(root, settings, local_safety=False)
            require(encode(actual) == encode(supplied), 'Workstation instructions refer to stale settings')
        raw = workstation_markdown(root, settings, _instruction_choices(root, settings))
        result['text'] = raw.decode('utf-8')
        observed = _setup_bytes(path, MAX_WORKSTATION_MARKDOWN_BYTES)
        stable = (_setup_bytes(settings_path, MAX_WORKSTATION_BYTES) == saved
                  and _setup_bytes(connections_path, 1024 * 1024) == connections
                  and _setup_bytes(path, MAX_WORKSTATION_MARKDOWN_BYTES) == observed)
        if saved is not None and observed == raw and stable:
            result.update(sha256=sha(raw), next_step=_WORKSTATION_NEXT_STEP, status='READY')
    except (ValidationError, OSError, UnicodeError):
        pass  # Never echo malformed configuration or a modified companion's contents.
    return result


def inspect_workstation(workspace, *, environ=None, origin=None):
    """Read the single form's values. Environment fallbacks are nonsecret and bounded."""
    with _LOCK:
        path = _workstation_path(workspace)
        settings = load_workstation_settings(workspace)
        if not path.exists():
            env = dict(os.environ if environ is None else environ)
            for field, variable in _CONNECTION_FIELDS.items():
                value = env.get(variable)
                if value:
                    try:
                        settings[field] = _validate_workstation(path.parent.parent, {field: value}, partial=True)[field]
                    except ValidationError:
                        pass  # Never echo a credential-bearing legacy URL or malformed alias.
            if settings['zowe_profile'] is None:
                settings['zowe_zosmf_profile'] = None
        view = _workstation_view(path.parent.parent, settings, saved=path.exists())
        from .connection_setup import inspect_connections
        view['connection_setup'] = inspect_connections(path.parent.parent, settings, origin)
        view['workflow']['claude_mcp_servers'] = view['connection_setup']['claude_mcp_servers']
        view['instructions'] = inspect_workstation_instructions(path.parent.parent, settings)
        return view


def prepare_workstation(workspace, settings, *, environ=None):
    """Validate a local settings write without changing exports, bindings or evidence."""
    with _LOCK:
        path = _workstation_path(workspace)
        root = path.parent.parent
        update = _validate_workstation(root, settings, partial=True)
        current = inspect_workstation(root, environ=environ)['settings']
        current.update(update)
        if current['source_mode'] == 'upload':
            current['source_folder'] = None
        current = _validate_workstation(root, current)
        if current['process_notes'] is not None:
            from .process_context import read_markdown
            require(Path(current['process_notes']).suffix.lower() == '.md',
                    'process_notes: select a Markdown .md file')
            read_markdown(current['process_notes'])
        view = _workstation_view(root, current, saved=True)
        require(not view['readiness']['remaining'],
                '; '.join(c['id'] + ': ' + c['message'] for c in view['checks'] if c['status'] == 'BLOCKED'))
        from .domain import encode
        document = {'version': 1, 'settings': current}
        encode(document, MAX_WORKSTATION_BYTES)
        return view, path, document



def save_workstation(workspace, settings, *, environ=None):
    with _LOCK:
        path = _workstation_path(workspace);root = path.parent.parent
        markdown_path = safe_path(root, '.migration/workstation.md')
        connections_path = safe_path(root, '.migration/connections.json')
        before = {path: _setup_bytes(path, MAX_WORKSTATION_BYTES),
                  markdown_path: _setup_bytes(markdown_path, MAX_WORKSTATION_MARKDOWN_BYTES)}
        connections_before = _setup_bytes(connections_path, 1024 * 1024)
        view, path, document = prepare_workstation(workspace, settings, environ=environ)
        markdown = workstation_markdown(root, view['settings'], _instruction_choices(root, view['settings']))
        prepared = [(path, encode(document)), (markdown_path, markdown)];changed = []
        try:
            require(all(_setup_bytes(p, max(MAX_WORKSTATION_BYTES, MAX_WORKSTATION_MARKDOWN_BYTES)) == raw
                        for p, raw in before.items()) and _setup_bytes(connections_path, 1024 * 1024) == connections_before,
                    'Setup changed during planning; reload before retrying Save')
            for destination, raw in prepared:
                require(_setup_bytes(destination, MAX_WORKSTATION_MARKDOWN_BYTES) == before[destination]
                        and _setup_bytes(connections_path, 1024 * 1024) == connections_before,
                        'Setup changed during Save; reload before retrying')
                if before[destination] != raw:
                    if destination == path:atomic_json(path, document)
                    else:atomic_bytes(destination, raw)
                    changed.append((destination, raw))
            from .connection_setup import inspect_connections
            view['connection_setup'] = inspect_connections(root, view['settings'])
            view['workflow']['claude_mcp_servers'] = view['connection_setup']['claude_mcp_servers']
            view['instructions'] = inspect_workstation_instructions(root, view['settings'])
            require(all(_setup_bytes(p, MAX_WORKSTATION_MARKDOWN_BYTES) == raw for p, raw in prepared)
                    and _setup_bytes(connections_path, 1024 * 1024) == connections_before
                    and view['instructions']['status'] == 'READY',
                    'Setup changed after publication; reload before retrying Save')
        except Exception:
            # Check the entire rollback set first. A concurrent valid edit must
            # never be overwritten or combined with a partial rollback.
            require(all(_setup_bytes(destination, MAX_WORKSTATION_MARKDOWN_BYTES) == raw
                        for destination, raw in changed),
                    'Setup changed during failed Save; preserve files and inspect local setup')
            for destination, raw in reversed(changed):
                require(_setup_bytes(destination, MAX_WORKSTATION_MARKDOWN_BYTES) == raw,
                        'Setup changed during rollback; preserve files and inspect local setup')
                if before[destination] is None:destination.unlink()
                else:atomic_bytes(destination, before[destination])
            raise
        return view


def intake_defaults(workspace):
    """Only future intake uses these mutable preferences; frozen runs stay unchanged."""
    settings = load_workstation_settings(workspace)
    return {'source_folder': settings['source_folder'] if settings['source_mode'] == 'folder' else None,
            'process_notes': settings['process_notes']}
