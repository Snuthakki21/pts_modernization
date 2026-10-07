"""Deterministic operator preparation; no source, credential or network access."""
import os
from pathlib import Path
import re
import shutil
import threading

from .domain import ValidationError, atomic_json, decode, require, safe_path
from .limits import MAX_SOURCE_BYTES, MAX_SOURCE_FILE_BYTES, MAX_SOURCE_FILES, MAX_SOURCE_LINES, MAX_UI_SOURCE_BYTES

MAX_SETUP_BYTES = 4096
_LOCK = threading.RLock()
_QUESTIONS = (
    ('source', 'Source export', 'How will you supply the complete read-only source export?',
     (('local_endeavor', 'Local Endeavor folder'), ('upload', 'Upload source files'), ('needs_setup', 'Help preparing the export'))),
    ('manifest', 'Process intake', 'Is the process manifest ready with ordered jobs and steps?',
     (('ready', 'Manifest ready'), ('needs_setup', 'Prepare the manifest'))),
    ('zowe', 'Read-only Zowe', 'Does Copilot need approved read-only Zowe retrieval for this process?',
     (('not_needed', 'Not needed'), ('configured', 'Configured locally'), ('needs_setup', 'Help configuring Zowe'))),
    ('db2', 'Read-only Db2', 'Does Copilot need approved read-only Db2 catalog retrieval for this process?',
     (('not_needed', 'Not needed'), ('configured', 'Configured locally'), ('needs_setup', 'Help configuring Db2'))),
    ('llm', 'Analysis workflow', 'Use Claude Code with local files and Copilot only for retrieval, or choose an explicit deterministic/provider alternative?',
     (('copilot_chat', 'Claude Code + Copilot retrieval (Recommended)'), ('disabled', 'Deterministic analysis'), ('opt_in', 'Legacy approved provider suggestions'))),
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
        'zowe':'Install the approved Zowe CLI. From the workspace, run tools/setup_zowe.py with your actual z/OSMF host, port and project profile aliases, then run zowe config secure interactively. Enter user/password only at local Zowe prompts. Set WB_ZOWE_PROFILE and the paired WB_ZOWE_ZOSMF_PROFILE before launch. Preserve explicitly selected project config/schema files; never read home profiles here. WEDLX is application location context, with availability and input readiness still Unknown.',
        'db2':'Prepare the read-only Db2 gateway with tools/setup_db2.py. Replace placeholders with actual nonsecret host, port and database values. Put the approved CA certificate at certificates/DB2-CA.cert and retain TLS validation. Supply authentication privately in the launch environment, then set WB_DB2_MCP_URL for the gateway. Configuration and a certificate file do not prove live access; setup never submits SQL.',
        'llm':'Claude Code reads approved local files and owns lineage analysis, development, testing and review with no MCP servers. GitHub Copilot in VS Code only retrieves requested source and metadata through already approved MCP connections into the exact local inbox. Return to Claude and say Continue; the existing Coordinator validates the files before resuming. Use python -m workbench.runner agent PROCESS_ID --workspace WORKSPACE for local task state. No model endpoint or API token is needed by this workflow. Actual credits remain Unknown without receipts. One authentic SME return and deterministic verification are still required.',
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
        require(not any(p.is_symlink() for p in (path, *path.parents)),
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
        present=bool(folder and not any(p.is_symlink() for p in (folder,*folder.parents)) and folder.is_dir())
        add('source_folder', 'READY' if present else 'BLOCKED',
            'Local export folder is available; its content is checked at intake.' if present else 'Select an existing source export folder.',
            '' if present else 'Enter the direct path to the complete local Endeavor export.')
    else:
        add('source_folder', 'READY', 'Upload source files when starting each process.')
    for field, label in (('process_notes', 'Process notes'), ('wedlx_folder', 'WEDLX folder'),
                         ('tran_repository_folder', 'Tran Repository folder')):
        value = settings[field]
        if value is None:
            add(field, 'NOT_CONFIGURED', label + ' is optional.')
        else:
            path=Path(value)
            safe=not any(p.is_symlink() for p in (path,*path.parents))
            available=safe and (path.is_file() if field == 'process_notes' else path.is_dir())
            add(field, 'READY' if available else 'BLOCKED',
                label + ' is available; business readiness remains unverified.' if available else label + ' is no longer available.',
                '' if available else 'Correct this path or clear the optional value and save.')
    require(settings['zowe_profile'] is not None or settings['zowe_zosmf_profile'] is None,
            'zowe_zosmf_profile: also select the approved base profile')
    for field, label in (('zowe_profile', 'Zowe profile'), ('db2_metadata_url', 'Db2 metadata endpoint')):
        add(field, 'UNVERIFIED' if settings[field] else 'NOT_CONFIGURED',
            label + ' is saved for approved Copilot retrieval; no connection was attempted.' if settings[field]
            else label + ' is optional; use existing approved Copilot connections when needed.')
    remaining = [c['id'] for c in checks if c['status'] == 'BLOCKED']
    if not saved:
        remaining.insert(0, 'save')
    return {'version': 1, 'saved': saved, 'settings': dict(settings), 'checks': checks,
            'readiness': {'status': 'NEEDS_SETUP' if remaining else 'READY_FOR_INTAKE',
                          'remaining': remaining, 'connectivity_verified': False,
                          'source_verified': False, 'conversion_verified': False},
            'workflow': {'assistant_mode': 'claude_files', 'copilot_role': 'retrieval_only',
                         'claude_mcp_servers': 0}, 'metrics': deterministic_metrics()}


def inspect_workstation(workspace, *, environ=None):
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
        return _workstation_view(path.parent.parent, settings, saved=path.exists())


def save_workstation(workspace, settings, *, environ=None):
    """One atomic save; setup does not alter exports, catalog bindings or process evidence."""
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
        atomic_json(path, document)
        return view


def intake_defaults(workspace):
    """Only future intake uses these mutable preferences; frozen runs stay unchanged."""
    settings = load_workstation_settings(workspace)
    return {'source_folder': settings['source_folder'] if settings['source_mode'] == 'folder' else None,
            'process_notes': settings['process_notes']}
