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
    ('zowe', 'Read-only Zowe', 'Do you need read-only Zowe discovery for this process?',
     (('not_needed', 'Not needed'), ('configured', 'Configured locally'), ('needs_setup', 'Help configuring Zowe'))),
    ('db2', 'Read-only Db2', 'Do you need read-only Db2 catalog discovery for this process?',
     (('not_needed', 'Not needed'), ('configured', 'Configured locally'), ('needs_setup', 'Help configuring Db2'))),
    ('llm', 'Analysis assistant', 'Use GitHub Copilot Chat after lineage discovery, or choose the existing deterministic/provider modes?',
     (('copilot_chat', 'GitHub Copilot Chat (Recommended)'), ('disabled', 'Deterministic analysis'), ('opt_in', 'Legacy approved provider suggestions'))),
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
    config['assistant_mode'] = 'deterministic' if answers['llm'] == 'disabled' else answers['llm'] or 'copilot_chat'
    actions = {
        'source':f'Choose the complete local Endeavor export (up to {MAX_SOURCE_FILES:,} files, {MAX_SOURCE_FILE_BYTES // (1024 * 1024)} MiB per file, {MAX_SOURCE_BYTES // (1024 * 1024)} MiB combined and {MAX_SOURCE_LINES:,} physical lines) or upload up to {MAX_UI_SOURCE_BYTES // (1024 * 1024)} MiB in the browser. Keep larger exports in local Endeavor; preserve every original file and never execute the source.',
        'manifest':'Download the intake template, supply the real process ID and ordered jobs/steps, then mark the manifest ready. Setup does not invent process facts.',
        'zowe':'Install the approved Zowe CLI. From the workspace, run tools/setup_zowe.py with your actual z/OSMF host, port and project profile aliases, then run zowe config secure interactively. Enter user/password only at local Zowe prompts. Set WB_ZOWE_PROFILE and the paired WB_ZOWE_ZOSMF_PROFILE before launch. Preserve explicitly selected project config/schema files; never read home profiles here. WEDLX is application location context, with availability and input readiness still Unknown.',
        'db2':'Prepare the read-only Db2 gateway with tools/setup_db2.py. Replace placeholders with actual nonsecret host, port and database values. Put the approved CA certificate at certificates/DB2-CA.cert and retain TLS validation. Supply authentication privately in the launch environment, then set WB_DB2_MCP_URL for the gateway. Configuration and a certificate file do not prove live access; setup never submits SQL.',
        'llm':'GitHub Copilot Chat needs no model endpoint or API token in this workbench. Complete selected-job lineage discovery first, then use the local MCP bridge in VS Code to retrieve the frozen task and source excerpts and submit source-grounded suggestions. Model identity and token usage remain Unknown. The one SME packet follows the validated handoff; actual human answers and deterministic tests remain required.',
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
