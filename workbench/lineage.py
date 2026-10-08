"""Job-led, bounded static mainframe object discovery.

This module maps source references; it neither executes mainframe operations nor
establishes conversion, input readiness, runtime behavior or estate completeness.
Only missing objects in the selected job closure are offered to a read-only
resolver. Every original export remains in the inventory, including unknowns.
"""
from collections import defaultdict, deque
from bisect import bisect_right
from pathlib import PurePosixPath, Path
import re

from .domain import encode, require, sha
from .mainframe import _lines, classify_files, load_knowledge, validate_snapshot
from .limits import (MAX_SOURCE_BYTES, MAX_SOURCE_FILES, MAX_SOURCE_FILE_BYTES,
                     MAX_SOURCE_LINES, source_line_count)


NAME = r'[A-Z@$#][A-Z0-9@$#_-]*'
QUALIFIED = NAME + r'(?:\.' + NAME + r')*'
SOURCE_KINDS = {'job', 'proc', 'program', 'copybook', 'jcl_include',
                'control_member', 'bms_mapset', 'bms_map', 'cics_transaction',
                'ca7_definition', 'mq_interface', 'db2_table'}
FILE_ROLES = {'cobol_program': 'program', 'copybook': 'copybook',
              'dclgen': 'copybook', 'jcl_job': 'job', 'jcl_proc': 'proc',
              'jcl_fragment': 'jcl_include', 'bms_map': 'bms_mapset',
              'utility_control': 'control_member'}
MAX_DISCOVERED_FILES = 1000
MAX_LOOKUPS = 1000
APPLICATION_LOCATIONS = ('WEDLX', 'Tran Repository')
PARSER_LIMITS = [
    'Static signatures only; not a COBOL, JCL, SQL, CICS, CA7 or MQ compiler.',
    'Dynamic calls, symbolic JCL operands, continuations and vendor-specific commands remain explicit gaps when encountered.',
    'SQL scope is explicit static table references; dynamic SQL, delimited identifiers and unqualified catalog identities need confirmation.',
    'DD datasets and application staging locations do not establish input data availability or readiness.',
    'Local definitions establish source presence, not installed resources, catalog coverage, scheduling or observed legacy behavior.',
    'Complete means the discovered closure of selected jobs under these parser rules; it is never proof of the complete application estate.',
]


def _mask_literals(text):
    """Retain offsets and line numbers while shielding keywords in literals."""
    result = list(text); i = 0
    while i < len(text):
        if text[i] not in "\"'": i += 1; continue
        quote = text[i]; result[i] = '?'; i += 1
        while i < len(text):
            char = text[i]; result[i] = '\n' if char == '\n' else ' '; i += 1
            if char == quote:
                if i < len(text) and text[i] == quote: result[i] = ' '; i += 1
                else: break
    return ''.join(result)


def _operand(text, start):
    value = text[start:].lstrip(); quoted = value.startswith(('"', "'"))
    if quoted:
        quote = value[0]; match = re.match(re.escape(quote) + r'((?:[^' + re.escape(quote) + r']|' + re.escape(quote * 2) + r')*)' + re.escape(quote), value)
        return (match[1].replace(quote * 2, quote), True) if match else (value, False)
    match = re.match(r'[^\s,()]+', value)
    return (match[0].rstrip('.') if match else ''), False


def _member_identity(name):
    """Separate an explicit library/member qualifier without inventing one."""
    name = name.upper().strip().strip("\"'")
    match = re.fullmatch('(' + QUALIFIED + r')\((' + NAME + r')\)', name, re.I)
    if match: return match[2], match[1]
    if '.' in name:
        return name.rsplit('.', 1)[-1], name.rsplit('.', 1)[0]
    return name, None


def _evidence(path, line, text, origin='source', **extra):
    return {'path': path, 'line': line, 'text': text[:1000], 'origin': origin, **extra}



def _cics_blocks(lines):
    """Bounded complete EXEC CICS spans; literals/comments cannot create commands."""
    by_line = dict(lines)
    text = '\n'.join(by_line.get(n, '') for n in range(1, max(by_line, default=0) + 1))
    masked = _mask_literals(text)
    starts = list(re.finditer(r'\bEXEC\s+CICS\b', masked, re.I))
    line_breaks = [-1, *[match.start() for match in re.finditer('\n', text)]]
    result = []
    for index, match in enumerate(starts):
        stop = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        end = re.search(r'\bEND-EXEC\b', masked[match.end():stop], re.I)
        finish = match.end() + end.end() if end else stop
        first = bisect_right(line_breaks, match.start())
        last = bisect_right(line_breaks, finish)
        bounded = finish - match.start() <= 65536 and last - first <= 500
        result.append({'line': first, 'end_line': last,
                       'text': text[match.start():min(finish, match.start() + 65536)],
                       'complete': bool(end) and bounded})
    return result


def _cics_operands(block):
    """Return typed literal/dynamic lookup obligations without inferring state semantics."""
    text = block['text']; masked = _mask_literals(text)
    if not block['complete']:
        return [('unknown_dependency', '<INCOMPLETE OR OVERSIZED EXEC CICS>', 'cics_command', True, None)]
    command = re.match(r'EXEC\s+CICS\s+([A-Z]+)(?:\s+(TS|TD))?\b', masked, re.I)
    if not command:return [('unknown_dependency', '<UNKNOWN EXEC CICS COMMAND>', 'cics_command', True, None)]
    verb = command[1].upper(); queue_type = (command[2] or '').upper()
    operands = {}; top_level = list(masked); depth = 0
    for offset, char in enumerate(masked):
        if depth:top_level[offset] = ' '
        if char == '(':depth += 1
        elif char == ')':depth = max(0, depth - 1)
    option_text = ''.join(top_level)
    form = re.match(r'\s+(MAP|TEXT|CONTROL)\b', masked[command.end():], re.I)
    for match in re.finditer(r'(?<![A-Z0-9@$#_-])(PROGRAM|MAP|MAPSET|FILE|DATASET|QUEUE|QNAME|TRANSID|CHANNEL|CONTAINER|SYSID)\s*\(', option_text, re.I):
        # Command options are top-level; names inside FROM/INTO expressions are data.
        value, quoted = _operand(text, match.end())
        name = value.upper()
        valid = quoted and len(name) <= 128 and bool(re.fullmatch(NAME, name, re.I))
        if len(name) > 128:name = '<CICS ' + match[1].upper() + ' OPERAND EXCEEDS 128 CHARACTERS>'
        key = {'DATASET': 'FILE', 'QNAME': 'QUEUE'}.get(match[1].upper(), match[1].upper())
        operands.setdefault(key, []).append((name or '<UNKNOWN ' + match[1].upper() + '>', not valid))
    out = []
    specs = {'PROGRAM': ('program', 'cics_link'), 'FILE': ('cics_file_definition', 'cics_file'),
             'TRANSID': ('cics_transaction', 'cics_transaction'),
             'CHANNEL': ('cics_channel', 'cics_channel'), 'CONTAINER': ('cics_container', 'cics_container'),
             'SYSID': ('cics_system', 'cics_remote_system')}
    for key, (kind, relationship) in specs.items():
        for name, dynamic in operands.get(key, []):out.append((kind, name, relationship, dynamic, None))
    mapsets = operands.get('MAPSET', [])
    mapset_tokens = list(re.finditer(r'(?<![A-Z0-9@$#_-])MAPSET(?![A-Z0-9@$#_-])', option_text, re.I))
    malformed_mapset = len(mapset_tokens) != len(mapsets)
    if malformed_mapset:
        out.append(('unknown_dependency', '<CICS ' + verb + ' MALFORMED MAPSET>', 'cics_command', True, None))
    for name, dynamic in mapsets:out.append(('bms_mapset', name, 'uses_mapset', dynamic, None))
    for name, dynamic in operands.get('MAP', []):
        # A dynamic mapset cannot be ignored even when one map name is unique locally.
        library = mapsets[0][0] if len(mapsets) == 1 and not mapsets[0][1] else None
        if not mapsets and not malformed_mapset and verb in ('SEND', 'RECEIVE'):
            # IBM SEND/RECEIVE MAP defaults the mapset to the MAP operand, not a
            # locally unique matching map or the process manifest's preferred mapset.
            library = name if not dynamic else None
            out.append(('bms_mapset', name, 'uses_default_mapset', dynamic, None))
        out.append(('bms_map', name, 'uses_map', dynamic or malformed_mapset or bool(mapsets and library is None), library))
    for name, dynamic in operands.get('QUEUE', []):
        kind = 'cics_tdqueue_definition' if queue_type == 'TD' else 'cics_tsqueue' if queue_type == 'TS' else 'cics_queue'
        out.append((kind, name, 'cics_queue', dynamic or not queue_type, None))
    required = {'LINK': 'PROGRAM', 'XCTL': 'PROGRAM', 'START': 'TRANSID',
                'READ': 'FILE', 'WRITE': 'FILE', 'REWRITE': 'FILE', 'DELETE': 'FILE',
                'STARTBR': 'FILE', 'READNEXT': 'FILE', 'READPREV': 'FILE', 'ENDBR': 'FILE',
                'READQ': 'QUEUE', 'WRITEQ': 'QUEUE', 'DELETEQ': 'QUEUE'}
    if verb in ('SEND', 'RECEIVE') and form and form[1].upper() == 'MAP':required[verb] = 'MAP'
    if verb in required and not operands.get(required[verb]):
        out.append(('unknown_dependency', '<CICS ' + verb + ' MISSING ' + required[verb] + '>', 'cics_command', True, None))
    # Commands without lookup operands stay source-semantic obligations in analysis.
    return out

def map_lineage(files, manifest, knowledge=None, resolver=None):
    """Return deterministic JSON metadata for the selected job object closure.

    ``files`` maps original relative paths to source text. ``resolver`` may be a
    callable or an object with ``resolve(request)``. A request names the missing
    typed object and source evidence and always says ``read_only_lookup``.
    Accepted source responses contain ``content``/``filename`` or a ``files``
    mapping, plus nonempty ``provenance``. Returned snapshots are data for the
    caller to freeze, never filesystem writes by this mapper. Dataset/catalog
    metadata requires an explicit resolved result with provenance. Incomplete
    resolver coverage remains a gap even when source was retrieved.
    """
    require(isinstance(files, dict) and all(isinstance(p, str) and isinstance(t, str) for p, t in files.items()),
            'Lineage requires text exports with path identities')
    require(isinstance(manifest, dict) and isinstance(manifest.get('jobs', []), list), 'Lineage requires a manifest job list')
    require(len(files) <= MAX_SOURCE_FILES, 'Lineage export exceeds the source file-count bound')
    require(all(len(t.encode('utf-8')) <= MAX_SOURCE_FILE_BYTES for t in files.values()),
            'Lineage export exceeds the source per-file byte bound')
    require(sum(len(t.encode('utf-8')) for t in files.values()) <= MAX_SOURCE_BYTES, 'Lineage export exceeds the source byte bound')
    require(sum(source_line_count(t) for t in files.values()) <= MAX_SOURCE_LINES,
            'Lineage export exceeds the source line bound')
    knowledge = knowledge if knowledge is not None else load_knowledge(Path(__file__).resolve().parent.parent)
    validate_snapshot(knowledge)
    cics_version=manifest.get('cics_contract_version')
    guided_version=manifest.get('guided_contract_version')
    require(cics_version is None or type(cics_version) is int and cics_version==1,'Unsupported frozen CICS screen contract')
    require(guided_version is None or type(guided_version) is int and guided_version==1,'Unsupported frozen guided intake contract')
    cics_v1=cics_version==1
    catalog_v1=cics_v1 or guided_version==1
    inventory_paths = sorted(files); sources = dict(files); classifications = classify_files(sources, manifest, knowledge)
    original_scope = manifest.get('original_source_files', manifest.get('authorization', {}).get('scope', files))
    require(isinstance(original_scope, (dict, list, tuple)) and set(original_scope).issubset(files),
            'Original source inventory must refer to retained files')
    original_paths = sorted(original_scope)
    nodes = {}; edges = []; outgoing = defaultdict(list); edge_keys = set(); index = defaultdict(list); aliases = defaultdict(list); members = defaultdict(list)
    frozen_provenance = manifest.get('discovery_provenance', {})
    require(isinstance(frozen_provenance, dict), 'Frozen discovery provenance requires a mapping')
    references = defaultdict(list); parsed = set(); provenance = {p: v for p, v in frozen_provenance.items() if p in files}
    snapshots = []; lookups = []; lookup_cache = {}
    source_bytes = sum(len(t.encode('utf-8')) for t in sources.values())
    source_lines = sum(source_line_count(t) for t in sources.values())
    gaps = []; selected = set(); visited = set(); root_nodes = []; cycles = []
    utilities = {name.upper() for group in (knowledge['catalog'], knowledge['application'])
                 for utility in group['utilities'] for name in [utility['name'], *utility['aliases']]}

    def node(kind, name, path=None, line=None, evidence=None, resolution='local_source', **extra):
        key = ('source_file:' + name if kind == 'source_file' else
               kind + ':' + (path + ':' if path else '') + name.upper() + (':' + str(line) if kind == 'jcl_step' else ''))
        if key not in nodes:
            nodes[key] = {'id': key, 'kind': kind, 'name': name, 'path': path,
                          'resolution': resolution, 'evidence': [], 'selected': False, **extra}
        if evidence and evidence not in nodes[key]['evidence']: nodes[key]['evidence'].append(evidence)
        return key

    def edge(source, target, kind, evidence, resolution='resolved', **extra):
        key = (source, target, kind, evidence.get('path'), evidence.get('line'), evidence.get('origin'))
        if key not in edge_keys:
            edge_keys.add(key); link = {'source': source, 'target': target, 'kind': kind,
                                       'evidence': [evidence], 'resolution': resolution, **extra}
            edges.append(link); outgoing[source].append(link)

    def declaration(path, kind, name, number, text, alias=True):
        ev = _evidence(path, number, text); ident = node(kind, name.upper(), path, evidence=ev)
        if ident not in index[kind, name.upper()]: index[kind, name.upper()].append(ident)
        if alias and (kind != 'program' or PurePosixPath(path).stem.upper() == name.upper()):
            stem = PurePosixPath(path).stem.upper()
            if ident not in aliases[kind, stem]: aliases[kind, stem].append(ident)
        file_id = 'source_file:' + path
        edge(file_id, ident, 'declares', ev); edge(ident, file_id, 'defined_in', ev)
        return ident

    def reference(source, kind, name, relationship, ev, dynamic=False, library=None, **extra):
        references[source].append({'source': source, 'kind': kind, 'name': name.upper(),
                                   'relationship': relationship, 'evidence': ev,
                                   'dynamic': dynamic, 'library': library, **extra})

    def parse(path):
        if path in parsed: return
        parsed.add(path); members[PurePosixPath(path).stem.upper()].append(path)
        text = sources[path]; file_id = 'source_file:' + path; current_mapset = None
        classification = classifications[path]
        catalog_receipt = None
        if catalog_v1:
            from .db2_catalog import table_description
            catalog_receipt = table_description(text, provenance.get(path))
            if catalog_receipt:classification = {**classification, 'kind': 'db2_catalog_evidence', 'conflicts': []};classifications[path] = classification
        node('source_file', path, evidence=_evidence(path, None, 'Source export inventory'),
             classification=classification['kind'], source_hash=sha(text),
             provenance=provenance.get(path, {'origin': 'local_repository_export', 'path': path}))
        if catalog_receipt:
            table_name = catalog_receipt['schema'] + '.' + catalog_receipt['table']
            table_id = declaration(path, 'db2_table', table_name, 1, 'Observed typed Db2 MCP table catalog receipt', False)
            nodes[table_id].update(catalog_evidence=catalog_receipt, executable_source=False, conversion_support='UNVERIFIED')
            # Table identity is observed even with partial columns. Full column/DDL
            # semantics remain named obligations in source analysis; they are not
            # a synthetic object kind no retrieval can ever declare.
            return
        lines = _lines(text); originals = text.splitlines(); declared = []; owner = file_id; jcl_owner = file_id; step = None; proc_stack = []
        if cics_v1 and classification['kind'] == 'unknown' and any(re.match(r'^\s*(?:DEFINE|ALTER)\s+(?:TDQUEUE|TSMODEL)\s*\(', _mask_literals(raw), re.I) for _, raw in lines):
            classification = {**classification, 'kind': 'cics_definition'};classifications[path] = classification;nodes[file_id]['classification'] = 'cics_definition'
        # Copybooks and fragments have dependency evidence rather than named declarations.
        role = FILE_ROLES.get(classification['kind'])
        if role in {'copybook', 'jcl_include', 'control_member'}:
            owner = declaration(path, role, PurePosixPath(path).stem, None, 'Member role from structural/dependency classification')
            declared.append(owner)
        sql_parts = []
        for number, raw in lines:
            masked = _mask_literals(raw); ev = _evidence(path, number, raw)
            original = originals[number - 1]
            if re.match(r'^[ 0-9]{6}-', original):
                reference(owner, 'unknown_dependency', 'FIXED_FORMAT_CONTINUATION', 'requires_interpretation', ev, True)
            pgm = re.match(r'^\s*PROGRAM-ID\s*\.\s*(' + NAME + r')\s*\.', masked, re.I)
            if pgm:
                owner = declaration(path, 'program', pgm[1], number, raw); declared.append(owner)
            jcl = re.match(r'^//(' + NAME + r')\s+(JOB|PROC)\b', masked, re.I)
            if jcl:
                if jcl[2].upper() == 'PROC': proc_stack.append(jcl_owner)
                jcl_owner = declaration(path, jcl[2].lower(), jcl[1], number, raw); declared.append(jcl_owner); step = None
            if re.match(r'^//\s+PEND\b', masked, re.I):
                jcl_owner = proc_stack.pop() if proc_stack else file_id; step = None
            execute = re.match(r'^//(' + NAME + r')?\s+EXEC\s+(.*)', raw, re.I)
            if execute:
                step = node('jcl_step', (execute[1] or '<unnamed>'), path, number, ev, owner=jcl_owner)
                edge(jcl_owner, step, 'contains_step', ev)
                operand = execute[2]; match = re.match(r'(PGM|PROC)\s*=\s*(.*)', operand, re.I)
                kind = 'program' if match and match[1].upper() == 'PGM' else 'proc'
                value, quoted = _operand(match[2] if match else operand, 0)
                name, library = _member_identity(value)
                dynamic = not bool(re.fullmatch(NAME, name, re.I)) or '&' in value
                reference(step, kind, name or value or '<unknown>', 'executes' if kind == 'program' else 'invokes_proc', ev, dynamic, library)
                if operand.rstrip().endswith(','):
                    reference(step, 'unknown_dependency', 'JCL_EXEC_CONTINUATION', 'requires_interpretation', ev, True)
            include = re.match(r'^//(?:' + NAME + r')?\s+INCLUDE\s+MEMBER\s*=\s*(.*)', raw, re.I)
            if include:
                value, _ = _operand(include[1], 0); name, library = _member_identity(value)
                reference(jcl_owner, 'jcl_include', name, 'includes', ev, not bool(re.fullmatch(NAME, name, re.I)), library)
            dd = re.match(r'^//(?:' + NAME + r')?\s+DD\b(.*)', raw, re.I)
            if dd:
                dsn = re.search(r'\b(?:DSN|DSNAME)\s*=\s*', _mask_literals(dd[1]), re.I)
                if dsn:
                    value, _ = _operand(dd[1], dsn.end())
                    # Parentheses are significant for member/GDG identities.
                    unquoted = dd[1][dsn.end():].lstrip()
                    if not unquoted.startswith(('"', "'")):
                        value = re.split(r'[,\s]', unquoted, 1)[0]
                    dynamic = '&' in value or not bool(re.fullmatch(QUALIFIED + r'(?:\((?:' + NAME + r'|[+-]?\d+)\))?', value, re.I))
                    dataset = value.upper()
                    reference(step or jcl_owner, 'dataset', dataset or '<unknown>', 'dd_dataset', ev, dynamic,
                              access='Unknown', readiness='Unknown')
                    member = re.fullmatch('(' + QUALIFIED + r')\((' + NAME + r')\)', value, re.I)
                    if member:
                        reference(step or jcl_owner, 'control_member', member[2], 'dd_member', ev, False, member[1])
                if re.match(r'\s*(?:DATA|\*)(?=\s|,|$)', dd[1], re.I):
                    control = node('in_stream_data', str(number), path, evidence=ev, resolution='literal_source', readiness='Unknown')
                    edge(step or jcl_owner, control, 'dd_instream_data', ev)
                    references[control].append({'source': control, 'kind': 'unknown_dependency', 'name': 'INSTREAM_CONTROL_DIALECT',
                                                'relationship': 'requires_interpretation', 'evidence': ev, 'dynamic': True, 'library': None})
                if dd[1].rstrip().endswith(','):
                    reference(step or jcl_owner, 'unknown_dependency', 'JCL_DD_CONTINUATION', 'requires_interpretation', ev, True)
            # Masking prevents CALL/COPY/SQL/CICS/MQ inside displayed data from becoming links.
            for call in re.finditer(r'\bCALL\s+(?=\S)', masked, re.I):
                value, quoted = _operand(raw, call.end()); name, library = _member_identity(value)
                if quoted and name in {'MQOPEN', 'MQPUT', 'MQPUT1', 'MQGET', 'MQCONN', 'MQCONNX', 'MQCLOSE', 'MQDISC', 'MQCMIT', 'MQBACK'}:
                    api = node('platform_api', name, evidence=ev, resolution='recognized_api', conversion_support='adapter_required')
                    edge(owner, api, 'calls', ev); continue
                reference(owner, 'program', name or '<unknown>', 'calls', ev,
                          not quoted or not bool(re.fullmatch(NAME, name, re.I)), library)
            if re.search(r'\bCALL\s*$', masked, re.I):
                reference(owner, 'program', '<continued CALL operand>', 'calls', ev, True)
            copy = re.match(r'^\s*COPY\s+(?=\S)', masked, re.I)
            if copy:
                value, _ = _operand(raw, copy.end()); name, library = _member_identity(value)
                qualifier = re.search(r'\b(?:OF|IN)\s+(' + QUALIFIED + r')', masked, re.I)
                reference(owner, 'copybook', name, 'copies', ev, not bool(re.fullmatch(NAME, name, re.I)), qualifier[1].upper() if qualifier else library)
            elif re.match(r'^\s*COPY\s*$', masked, re.I):
                reference(owner, 'copybook', '<continued COPY operand>', 'copies', ev, True)
            sql_include = re.search(r'\bEXEC\s+SQL\s+INCLUDE\s+(' + NAME + r')', masked, re.I)
            if sql_include: reference(owner, 'copybook', sql_include[1], 'sql_includes', ev)
            bms = re.match(r'^\s*(' + NAME + r')\s+DFHM(SD|DI)\b', masked, re.I)
            if bms:
                kind = 'bms_mapset' if bms[2].upper() == 'SD' else 'bms_map'
                ident = declaration(path, kind, bms[1], number, raw); declared.append(ident)
                if kind == 'bms_mapset': current_mapset = bms[1].upper()
                else: nodes[ident]['mapset'] = current_mapset
            resource_types = 'TRANSACTION|PROGRAM|MAPSET|FILE|TDQUEUE|TSMODEL' if cics_v1 else 'TRANSACTION|PROGRAM|MAPSET|FILE'
            cics = re.match(r'^\s*(?:DEFINE|ALTER)\s+(' + resource_types + r')\s*\(\s*(' + NAME + r')\s*\)', masked, re.I)
            if cics:
                kind = {'TRANSACTION': 'cics_transaction', 'PROGRAM': 'cics_program_definition', 'MAPSET': 'cics_mapset_definition', 'FILE': 'cics_file_definition', 'TDQUEUE': 'cics_tdqueue_definition', 'TSMODEL': 'cics_tsmodel_definition'}[cics[1].upper()]
                ident = declaration(path, kind, cics[2], number, raw, False); declared.append(ident)
                binding = re.search(r'\bPROGRAM\s*\(\s*(' + NAME + r')\s*\)', masked[cics.end():], re.I)
                if binding and not cics_v1: reference(ident, 'program', binding[1], 'binds_program', ev)
                if kind == 'cics_mapset_definition': reference(ident, 'bms_mapset', cics[2], 'defines_mapset', ev)
            if not cics_v1:
                for command in re.finditer(r'\b(?:LINK|XCTL)\s+PROGRAM\s*\(', masked, re.I):
                    value, quoted = _operand(raw, command.end()); name, library = _member_identity(value)
                    reference(owner, 'program', name or '<unknown>', 'cics_link', ev, not quoted or not bool(re.fullmatch(NAME, name, re.I)), library)
                if re.search(r'\bEXEC\s+CICS\s+(?:LINK|XCTL)\b', masked, re.I) and not re.search(r'\bPROGRAM\s*\(', masked, re.I):
                    reference(owner, 'program', '<continued CICS PROGRAM operand>', 'cics_link', ev, True)
                for command in re.finditer(r'\b(?:SEND|RECEIVE)\s+MAP\s*\(', masked, re.I):
                    value, quoted = _operand(raw, command.end()); name, _ = _member_identity(value)
                    mapset = re.search(r'\bMAPSET\s*\(', masked[command.end():], re.I)
                    mapset_name = None
                    if mapset:
                        mapset_value, mapset_quoted = _operand(raw, command.end() + mapset.end()); mapset_name, _ = _member_identity(mapset_value)
                        reference(owner, 'bms_mapset', mapset_name, 'uses_mapset', ev, not mapset_quoted)
                    reference(owner, 'bms_map', name or '<unknown>', 'uses_map', ev,
                              not quoted or not bool(re.fullmatch(NAME, name, re.I)), mapset_name)
            schedule = re.match(r'^\s*(?:JOB|LJOB|LQ|LPRRN)\s*,\s*JOB\s*=\s*(' + NAME + r')', masked, re.I)
            if schedule:
                ident = declaration(path, 'ca7_definition', schedule[1], number, raw, False); declared.append(ident)
                reference(ident, 'job', schedule[1], 'schedules_job', ev)
                for dep in re.finditer(r'\b(?:PRED|PREDECESSOR|DEPJOB|JOBDEP)\s*=\s*(' + NAME + r')', masked, re.I):
                    reference(ident, 'job', dep[1], 'job_dependency', ev)
            mq_definition = re.match(r'^\s*DEFINE\s+(?:QLOCAL|QREMOTE|QALIAS|CHANNEL)\s*\(\s*', masked, re.I)
            if mq_definition:
                value, _ = _operand(raw, mq_definition.end())
                if re.fullmatch(QUALIFIED, value, re.I):
                    ident = declaration(path, 'mq_interface', value, number, raw, False); declared.append(ident)
                else: reference(file_id, 'mq_interface', value or '<unknown queue>', 'defines_mq', ev, True)
            mq_call = re.search(r'\bCALL\s+\?', masked, re.I)
            if mq_call:
                value, quoted = _operand(raw, mq_call.end() - 1)
                if quoted and value.upper() in {'MQOPEN', 'MQPUT', 'MQPUT1', 'MQGET', 'MQCONN', 'MQCONNX'}:
                    reference(owner, 'mq_interface', '<dynamic queue binding>', 'uses_mq', ev, True)
            table = re.search(r'\b(?:CREATE|DECLARE)\s+TABLE\s+(' + QUALIFIED + r')|\bDECLARE\s+(' + QUALIFIED + r')\s+TABLE\b', masked, re.I)
            if table:
                ident = declaration(path, 'db2_table', table[1] or table[2], number, raw, False); declared.append(ident)
            # Only SQL files and actual EXEC SQL regions can supply table references.
            sql_parts.append((number, raw, masked, owner))
        raw_text = '\n'.join(raw for _, raw in lines)
        source_masked = '\n'.join(_mask_literals(raw) for _, raw in lines)
        offsets = [number for number, _ in lines]
        # CSD resource operands commonly occupy several physical records.
        if cics_v1:
            program_owners = [d for d in declared if nodes[d]['kind'] == 'program']
            program_lines = [nodes[d]['evidence'][0]['line'] for d in program_owners]
            for block in _cics_blocks(lines):
                owner_index = bisect_right(program_lines, block['line']) - 1
                command_owner = program_owners[owner_index] if owner_index >= 0 else file_id
                ev = _evidence(path, block['line'], block['text'], end_line=block['end_line'])
                for kind, name, relationship, dynamic, library in _cics_operands(block):
                    reference(command_owner, kind, name, relationship, ev, dynamic, library)
        resource_commands = list(re.finditer(r'(?m)^\s*(?:DEFINE|ALTER|DELETE|LIST)\s+\w+\s*\(', source_masked, re.I))
        for position, command in enumerate(resource_commands):
            finish = resource_commands[position + 1].start() if position + 1 < len(resource_commands) else len(source_masked)
            segment = source_masked[command.start():finish]
            if cics_v1:
                resource = re.match(r'\s*(?:DEFINE|ALTER)\s+(FILE|TDQUEUE)\s*\(\s*(' + NAME + r')\s*\)', segment, re.I)
                if resource:
                    start_index = source_masked.count('\n', 0, command.start())
                    number = offsets[start_index]
                    kind = 'cics_file_definition' if resource[1].upper() == 'FILE' else 'cics_tdqueue_definition'
                    resource_id = declaration(path, kind, resource[2], number, originals[number - 1], False)
                    attributes = {'DSNAME': ('dataset', 'cics_dataset'), 'INDIRECTNAME': ('cics_tdqueue_definition', 'cics_indirect_queue')}
                    for attribute, (target_kind, relation) in attributes.items():
                        match = re.search(r'\b' + attribute + r'\s*\(', segment, re.I)
                        if match:
                            value, _ = _operand(raw_text, command.start() + match.end())
                            valid = bool(re.fullmatch(QUALIFIED if target_kind == 'dataset' else NAME, value, re.I))
                            reference(resource_id, target_kind, value or '<UNKNOWN ' + attribute + '>', relation,
                                      _evidence(path, number, originals[number - 1], end_line=offsets[source_masked.count('\n', 0, command.start() + match.end())]), not valid)
            transaction = re.match(r'\s*(?:DEFINE|ALTER)\s+TRANSACTION\s*\(\s*(' + NAME + r')\s*\)', segment, re.I)
            if cics_v1 and transaction:
                bindings = list(re.finditer(r'\bPROGRAM\s*\(', segment, re.I))
                start_index = source_masked.count('\n', 0, command.start())
                number = offsets[start_index]
                ident = declaration(path, 'cics_transaction', transaction[1], number, originals[number - 1], False)
                for binding in bindings:
                    end_index = source_masked.count('\n', 0, command.start() + binding.end())
                    value, _ = _operand(raw_text, command.start() + binding.end())
                    valid = bool(re.fullmatch(NAME, value, re.I)) and len(value) <= 128
                    reference(ident, 'program', value or '<UNKNOWN CSD PROGRAM>', 'binds_program',
                              _evidence(path, number, originals[number - 1], end_line=offsets[end_index]), not valid)
                if len(bindings) > 1:
                    reference(ident, 'unknown_dependency', '<TRANSACTION ' + transaction[1].upper() + ' DUPLICATE PROGRAM BINDING>',
                              'requires_transaction_binding', _evidence(path, number, originals[number - 1],
                              end_line=offsets[source_masked.count('\n', 0, command.start() + bindings[-1].end())]), True)
            else:
                binding = re.search(r'\bPROGRAM\s*\(\s*(' + NAME + r')\s*\)', segment, re.I)
                if transaction and binding:
                    start_index = source_masked.count('\n', 0, command.start())
                    end_index = source_masked.count('\n', 0, command.start() + binding.end())
                    if start_index != end_index:
                        number = offsets[start_index]; end_number = offsets[end_index]
                        ident = declaration(path, 'cics_transaction', transaction[1], number, originals[number - 1], False)
                        reference(ident, 'program', binding[1], 'binds_program',
                                  _evidence(path, number, originals[number - 1], end_line=end_number))
        if role in {'job', 'proc', 'program', 'bms_mapset'} and not any(nodes[d]['kind'] == role for d in declared):
            # A conflicting suffix never manufactures a declaration.
            pass
        sql_active = classification['kind'] in {'sql', 'dclgen'}
        sql_lines = []
        for number, raw, masked, sql_owner in sql_parts:
            if re.search(r'\bEXEC\s+SQL\b', masked, re.I): sql_active = True
            if sql_active: sql_lines.append((number, raw, masked, sql_owner))
            if re.search(r'\bEND-EXEC\b', masked, re.I): sql_active = classification['kind'] in {'sql', 'dclgen'}
        sql_by_line = {number: (raw, masked, sql_owner) for number, raw, masked, sql_owner in sql_lines}
        sql_text = '\n'.join(sql_by_line.get(number, ('', '', owner))[1] for number in range(1, len(originals) + 1))
        # Mask dynamic statement operands before identifying static references.
        sql_static = re.sub(r'\b(?:PREPARE|EXECUTE\s+IMMEDIATE)\b[^;]*?(?=END-EXEC|;|$)',
                            lambda match: ''.join('\n' if c == '\n' else ' ' for c in match[0]), sql_text, flags=re.I)
        sql_static = re.sub(r'\bEND-EXEC\b', '?END-EXEC', sql_static, flags=re.I)
        for match in re.finditer(r'\b(?:CREATE\s+TABLE\s+(' + QUALIFIED + r')|DECLARE\s+(' + QUALIFIED + r')\s+TABLE)\b', sql_static, re.I):
            number = sql_static.count('\n', 0, match.start()) + 1
            raw, _, _ = sql_by_line[number]
            declaration(path, 'db2_table', match[1] or match[2], number, raw, False)
        cte_names = {m[1].upper() for m in re.finditer(r'\bWITH\s+(' + NAME + r')\s+AS\s*\(', sql_text, re.I)}
        for match in re.finditer(r'\b(?:FROM|JOIN|INTO|UPDATE|REFERENCES)\s+(' + QUALIFIED + r')', sql_static, re.I):
            name = match[1].upper()
            if name in cte_names or name in {'FINAL', 'OLD', 'NEW', 'TABLE', 'SELECT', 'VALUES', 'SET', 'JOIN', 'WHERE', 'ON', 'GROUP', 'ORDER', 'LATERAL'}: continue
            number = sql_static.count('\n', 0, match.start()) + 1
            raw, _, sql_owner = sql_by_line[number]
            reference(sql_owner, 'db2_table', name, 'sql_table', _evidence(path, number, raw,
                      end_line=sql_static.count('\n', 0, match.end()) + 1))
        for match in re.finditer(r'\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+\?', sql_static, re.I):
            number = sql_static.count('\n', 0, match.start()) + 1
            end_number = sql_static.count('\n', 0, match.end()) + 1
            raw, _, sql_owner = sql_by_line[number]
            if end_number in sql_by_line and any(q in sql_by_line[end_number][0] for q in ('"', "'")):
                reference(sql_owner, 'db2_table', '<delimited SQL identifier>', 'sql_table',
                          _evidence(path, number, raw, end_line=end_number), True)
        for number, raw, masked, sql_owner in sql_lines:
            ev = _evidence(path, number, raw)
            if re.search(r'\b(?:PREPARE|EXECUTE\s+IMMEDIATE)\b', masked, re.I):
                reference(sql_owner, 'db2_table', '<dynamic SQL>', 'dynamic_sql', ev, True)
            if re.search(r'\bWITH\s+' + NAME + r'\s+AS\s*\(', masked, re.I):
                reference(sql_owner, 'unknown_dependency', 'SQL_CTE_SCOPE', 'requires_interpretation', ev, True)
            if re.search(r'\bFROM\s+[^;]*,', masked, re.I):
                reference(sql_owner, 'unknown_dependency', 'SQL_COMPLEX_FROM', 'requires_interpretation', ev, True)
        # Reverse application bindings allow a selected PGM to discover its CICS/CA7 context.
        # They are connected after all local declarations have been indexed.

    def candidates(ref):
        kind, name = ref['kind'], ref['name']
        result = list(dict.fromkeys(index[kind, name] + aliases[kind, name]))
        if kind == 'control_member':
            result = list(dict.fromkeys(result + index['jcl_include', name] + aliases['jcl_include', name]))
        if not result and kind in {'copybook', 'jcl_include', 'control_member'}:
            # Existing unknown members are reviewed locally; they are not missing files.
            for path in members[name]:
                if classifications[path]['kind'] == 'unknown':
                    result.append(declaration(path, kind, name, None, 'Local member existence; dependency role requires parser confirmation'))
        if ref.get('library'):
            library = ref['library'].upper(); parts = set(re.split(r'[./]', library))
            if kind == 'bms_map': result = [ident for ident in result if nodes[ident].get('mapset') == library]
            else:
                result = [ident for ident in result if
                          library in nodes['source_file:' + nodes[ident]['path']]['provenance'].get('dataset', '').upper()
                          or parts.issubset(set(re.split(r'[./]', str(PurePosixPath(nodes[ident]['path']).parent).upper())))]
        return sorted(result)

    for path in inventory_paths: parse(path)
    location_context = manifest.get('application_input_locations', {})
    require(isinstance(location_context, dict), 'Application input locations require a mapping')
    location_facts = []
    input_bindings = {}
    for name in APPLICATION_LOCATIONS:
        fact = location_context.get(name, location_context.get(name.replace(' ', ''), {}))
        require(isinstance(fact, dict), 'Application input location evidence requires an object')
        evidence = fact.get('evidence', [])
        # A configured path is a location identity, not an observation that a file is ready.
        location = {'name': name, 'location_type': fact.get('location_type', 'local_or_mounted_file_share' if name == 'WEDLX' else 'application_staging_location'),
                    'physical_path': fact.get('path') or 'Unknown', 'dataset_name': 'Unknown',
                    'availability': fact.get('availability', 'Unknown') if evidence else 'Unknown',
                    'readiness': 'Unknown',
                    'evidence': evidence, 'basis': 'user_supplied_application_context'}
        location_facts.append(location)
        for observation in evidence:
            if not isinstance(observation, dict): continue
            for binding in observation.get('bindings', []):
                if (isinstance(binding, dict) and binding.get('logical_id') and
                        binding.get('basis') == 'READ_ONLY_FILE_METADATA_NO_BUSINESS_READINESS_CLAIM'):
                    input_bindings.setdefault(str(binding['logical_id']).upper(), []).append(
                        {'location': name, 'physical_path': location['physical_path'], 'binding': binding, 'observation': observation})
        node('input_location', name, evidence=_evidence(None, None,
             'User supplied application input-availability/staging location', 'user_supplied_context'),
             resolution='application_context', **{key: value for key, value in location.items() if key not in {'name', 'evidence'}})
        nodes['input_location:' + name.upper()]['availability_evidence'] = evidence

    # Add local binding context without treating every exported application object as selected.
    context_links = []
    for refs in references.values():
        for ref in refs:
            if ref['relationship'] in {'binds_program', 'schedules_job'}:
                for target in candidates(ref): context_links.append((target, ref['source'], ref['evidence']))
    for target, context, ev in context_links: edge(target, context, 'has_application_binding', ev)

    source_step_kinds = {}
    for step_id, refs in references.items():
        step_node = nodes.get(step_id, {})
        owner_node = nodes.get(step_node.get('owner'), {})
        if step_node.get('kind') == 'jcl_step' and owner_node.get('kind') == 'job':
            for ref in refs:
                if ref['relationship'] in {'executes', 'invokes_proc'}:
                    source_step_kinds[owner_node['name'], step_node['name'].upper(), ref['name']] = ref['kind']

    for tx in manifest.get('transactions', []):
        ev = _evidence(None, None, tx['id'], 'manifest')
        root = node('manifest_transaction', tx['id'], evidence=ev, resolution='manifest_declaration')
        root_nodes.append(root)
        reference(root, 'program', tx['program'], 'transaction_entry', ev)
        if cics_v1:
            resources = index['cics_transaction', tx['id']]
            entries = index['program', tx['program']]
            actual_cics = any(_cics_blocks(_lines(sources[nodes[d]['path']])) for d in entries)
            if resources or tx.get('mapset') or actual_cics:
                reference(root, 'cics_transaction', tx['id'], 'transaction_resource', ev)
            bindings = [ref for resource in resources for ref in references[resource]
                        if ref['relationship'] == 'binds_program']
            if resources and (not bindings or any(ref['name'] != tx['program'] for ref in bindings)):
                binding_evidence = bindings[0]['evidence'] if bindings else nodes[resources[0]]['evidence'][0]
                reference(root, 'unknown_dependency', '<TRANSACTION ' + tx['id'] + ' PROGRAM BINDING CONFLICT>',
                          'requires_transaction_binding', _evidence(binding_evidence['path'], binding_evidence['line'],
                          'Manifest ' + tx['id'] + ' -> ' + tx['program'] + '; resource bindings: '
                          + (', '.join(ref['name'] for ref in bindings) if bindings else 'no static PROGRAM binding'),
                          'manifest_and_source', expected_program=tx['program'],
                          observed_programs=[ref['name'] for ref in bindings],
                          binding_source_refs=[ref['evidence'] for ref in bindings] or [binding_evidence]), True)
        if tx.get('mapset'):
            reference(root, 'bms_mapset', tx['mapset'], 'transaction_mapset', ev)
            reference(root, 'bms_map', tx['map'], 'transaction_map', ev, library=tx['mapset'])
    for job in manifest.get('jobs', []):
        require(isinstance(job, dict) and isinstance(job.get('name'), str), 'Lineage jobs require a name')
        name = job['name'].upper(); ev = _evidence(None, None, name, 'manifest', job=name)
        root = node('manifest_job', name, evidence=ev, resolution='manifest_declaration')
        root_nodes.append(root); reference(root, 'job', name, 'selects_job', ev)
        for step in job.get('steps', []):
            require(isinstance(step, dict) and isinstance(step.get('program'), str), 'Lineage steps require a program')
            step_ev = _evidence(None, None, step['program'], 'manifest', job=name, step=step.get('name', ''))
            # A manifest PGM may actually be a PROC; local source disambiguates first.
            kind = source_step_kinds.get((name, step.get('name', '').upper(), step['program'].upper()), 'program')
            if not index['program', step['program'].upper()] and (index['proc', step['program'].upper()] or aliases['proc', step['program'].upper()]): kind = 'proc'
            reference(root, kind, step['program'], 'manifest_step', step_ev)
            for field, relation in [('inputs', 'input_context'), ('outputs', 'output_context')]:
                for value in step.get(field, []):
                    if value.casefold().replace(' ', '') in {location.casefold().replace(' ', '') for location in APPLICATION_LOCATIONS}:
                        location = next(x for x in APPLICATION_LOCATIONS if x.casefold().replace(' ', '') == value.casefold().replace(' ', ''))
                        edge(root, 'input_location:' + location.upper(), relation, step_ev)
                    else:
                        ident = node('input_data' if field == 'inputs' else 'output_data', value,
                                     evidence=step_ev, resolution='manifest_context', readiness='Unknown', dataset_name='Unknown')
                        edge(root, ident, relation, step_ev)

    pending = deque(sorted(root_nodes)); attempts = 0

    def add_gap(ref, reason, status, candidates_list=None):
        gap = {'kind': ref['kind'], 'name': ref['name'], 'source': ref['source'],
               'relationship': ref['relationship'], 'status': status, 'reason': reason,
               'evidence': [ref['evidence']], 'candidates': candidates_list or [],
               'local_repository_checked': True}
        if manifest.get('sme_packet_version',1)>=4 and ref['name'][:1] in ('I','Z'):
            alternate=('Z' if ref['name'].startswith('I') else 'I')+ref['name'][1:]
            gap['environment_candidates']=[{'node':n['id'],'name':n['name'],'path':n.get('path'),'status':'UNVERIFIED_ENVIRONMENT_RELATIONSHIP'} for n in nodes.values() if n['kind']==ref['kind'] and n['name']==alternate]
            if gap['environment_candidates']:gap['environment_mapping_requirement']='Confirm library/environment/version identity and call-site applicability; prefix similarity cannot resolve this binding'
        if gap not in gaps: gaps.append(gap)
        ident = node(ref['kind'], ref['name'], evidence=ref['evidence'], resolution=status,
                     candidates=candidates_list or [])
        edge(ref['source'], ident, ref['relationship'], ref['evidence'], status)
        selected.add(ident)

    def lookup(ref):
        nonlocal attempts
        key = (ref['kind'], ref['name'], ref.get('library'))
        if key in lookup_cache: return lookup_cache[key]
        if resolver is None or attempts >= MAX_LOOKUPS:
            response = {'status': 'UNAVAILABLE', 'reason': 'Read-only resolver is not configured' if resolver is None else 'Read-only lookup bound reached'}
        else:
            request = {'kind': ref['kind'], 'name': ref['name'], 'library': ref.get('library'),
                       'source': ref['evidence']['path'], 'source_path': ref['evidence']['path'],
                       'evidence': [ref['evidence']], 'operation': 'read_only_lookup',
                       'local_repository_checked': True}
            attempts += 1
            try:
                response = resolver.resolve(request) if hasattr(resolver, 'resolve') else resolver(request)
                if not isinstance(response, dict): response = {'status': 'UNRESOLVED', 'reason': 'Resolver returned no typed evidence'}
            except Exception as exc:
                # An authentication/network error must preserve the local map and gap.
                response = {'status': 'UNAVAILABLE', 'reason': 'Read-only lookup failed: ' + type(exc).__name__}
        lookup_cache[key] = response
        lookups.append({'kind': ref['kind'], 'name': ref['name'], 'library': ref.get('library'),
                        'status': str(response.get('status', 'UNRESOLVED')).upper(),
                        'provenance': response.get('provenance', {}), 'reason': response.get('reason', ''),
                        'operation': 'read_only_lookup'})
        return response

    while pending:
        ident = pending.popleft()
        if ident in visited: continue
        visited.add(ident); selected.add(ident)
        if ident.startswith('source_file:'):
            path = ident[len('source_file:'):]
            classification = classifications[path]
            if classification['kind'] in {'unknown', 'ambiguous', 'rexx', 'clist', 'pli', 'assembler'}:
                ref = {'kind': 'source_file', 'name': path, 'source': ident, 'relationship': 'source_interpretation',
                       'evidence': _evidence(path, None, 'Selected source needs a supported structural parser')}
                add_gap(ref, 'Selected export is ' + classification['kind'] + '; static dependency closure is not established', 'unresolved_parser')
        for link in list(outgoing[ident]):
            if link['source'] == ident and link['resolution'] == 'resolved':
                if link['target'] in visited and link['kind'] in {'defined_in', 'declares'}: continue
                pending.append(link['target'])
        for ref in references[ident]:
            if ref.get('dynamic'):
                add_gap(ref, 'Dynamic, symbolic or unsupported binding requires actual identity evidence', 'dynamic_unknown'); continue
            found = candidates(ref)
            if len(found) > 1:
                add_gap(ref, 'Multiple local definitions match; select the actual library/member', 'ambiguous', found); continue
            if not found and ref['kind'] == 'program' and ref['name'] in utilities:
                utility = node('utility', ref['name'], evidence=ref['evidence'], resolution='catalog_recognized', conversion_support='adapter_required')
                edge(ident, utility, ref['relationship'], ref['evidence']); pending.append(utility); continue
            if ref['kind'] == 'dataset' and ref['name'] in input_bindings:
                bindings = input_bindings[ref['name']]
                available = [b for b in bindings if b['binding'].get('available') is True]
                if len(available) == 1:
                    dataset = node('dataset', ref['name'], evidence=ref['evidence'], resolution='read_only_input_metadata',
                                   provenance=available[0], readiness='Unknown', availability='AVAILABLE')
                    edge(ident, dataset, ref['relationship'], ref['evidence']); pending.append(dataset)
                else:
                    add_gap(ref, 'Configured file-share input binding is unavailable or ambiguous; source presence cannot establish input availability',
                            'input_unavailable' if not available else 'ambiguous', [b['location'] for b in available])
                continue
            response = None
            if not found:
                response = lookup(ref); returned = response.get('files', {})
                if response.get('content') is not None:
                    returned = {response.get('filename') or ('discovered/' + ref['name']): response['content']}
                trusted = bool(response.get('provenance')) and str(response.get('status', '')).upper() == 'RESOLVED'
                if returned and trusted:
                    require(isinstance(returned, dict), 'Resolver source files must be a mapping')
                    for path, content in sorted(returned.items()):
                        valid_path = (isinstance(path, str) and bool(path) and not PurePosixPath(path).is_absolute()
                                      and '..' not in PurePosixPath(path).parts and '\\' not in path and ':' not in path)
                        if not valid_path or not isinstance(content, str): continue
                        if path in sources:
                            if sources[path] != content:
                                add_gap(ref, 'Retrieved snapshot conflicts with an existing immutable path', 'source_conflict')
                            continue
                        content_bytes = len(content.encode('utf-8'))
                        content_lines = source_line_count(content)
                        if (len(sources) - len(original_paths) >= MAX_DISCOVERED_FILES or len(sources) >= MAX_SOURCE_FILES
                                or content_bytes > MAX_SOURCE_FILE_BYTES or source_bytes + content_bytes > MAX_SOURCE_BYTES
                                or source_lines + content_lines > MAX_SOURCE_LINES):
                            add_gap(ref, 'Read-only source discovery bound reached', 'bounded_discovery'); continue
                        sources[path] = content; provenance[path] = response['provenance']; source_bytes += content_bytes; source_lines += content_lines
                        classifications.update(classify_files({path: content}, manifest, knowledge)); parse(path)
                        # A requested COPY member may contain procedural source with no signature.
                        if ref['kind'] in {'copybook', 'jcl_include', 'control_member'} and classifications[path]['kind'] == 'unknown':
                            classifications[path]['kind'] = {'copybook': 'copybook', 'jcl_include': 'jcl_fragment', 'control_member': 'utility_control'}[ref['kind']]
                            nodes['source_file:' + path]['classification'] = classifications[path]['kind']
                            declaration(path, ref['kind'], PurePosixPath(path).stem, None, 'Retrieved member role from the source dependency')
                        snapshots.append({'path': path, 'text': content, 'source_hash': sha(content), 'provenance': response['provenance']})
                    found = candidates(ref)
                if not found and ref['kind'] in {'dataset', 'db2_table', 'cics_transaction', 'ca7_definition', 'mq_interface'} and trusted and not returned:
                    external = node(ref['kind'], ref['name'], evidence=ref['evidence'], resolution='read_only_metadata',
                                    provenance=response['provenance'], metadata=response.get('metadata', {}),
                                    readiness='Unknown' if ref['kind'] == 'dataset' else None)
                    edge(ident, external, ref['relationship'], ref['evidence']); pending.append(external)
                    if str(response.get('coverage', 'PARTIAL')).upper() != 'COMPLETE':
                        add_gap(ref, 'Resolver supplied bounded metadata without complete identity/coverage evidence', 'partial_discovery')
                    continue
            if len(found) == 1:
                edge(ident, found[0], ref['relationship'], ref['evidence']); pending.append(found[0])
                if response and str(response.get('coverage', 'COMPLETE')).upper() != 'COMPLETE':
                    add_gap(ref, 'Retrieved source has incomplete discovery coverage', 'partial_discovery')
            elif len(found) > 1:
                add_gap(ref, 'Read-only lookup returned multiple matching source definitions', 'ambiguous', found)
            else:
                add_gap(ref, (response or {}).get('reason') or 'Required object is absent from the local repository and read-only lookup did not resolve it',
                        'missing' if ref['kind'] in SOURCE_KINDS and ref['kind'] != 'dataset' else 'unverified')

    for ident in selected:
        if ident in nodes: nodes[ident]['selected'] = True
    selected_paths = sorted(ident[len('source_file:'):] for ident in selected if ident.startswith('source_file:'))
    # Detect true object dependency cycles iteratively; defined_in/declares inventory links are not cycles.
    dependencies = defaultdict(set)
    for link in edges:
        if link['kind'] in {'calls', 'copies', 'includes', 'invokes_proc', 'job_dependency'} and link['resolution'] == 'resolved':
            dependencies[link['source']].add(link['target'])
            owner = nodes.get(link['source'], {}).get('owner')
            if owner: dependencies[owner].add(link['target'])
    # A source-owner COPY cycle is projected through the declaration's file role.
    for path in selected_paths:
        file_id = 'source_file:' + path
        decls = [d for d in nodes if nodes[d].get('path') == path and nodes[d]['kind'] in {'copybook', 'proc', 'program', 'jcl_include'}]
        for ref in references[file_id]:
            for target in candidates(ref):
                for declaration_id in decls: dependencies[declaration_id].add(target)
    colors = {}; stack = []
    for start in sorted(dependencies):
        if colors.get(start): continue
        colors[start] = 1; stack.append((start, iter(sorted(dependencies[start])))); trail = [start]
        while stack:
            current, children = stack[-1]
            child = next(children, None)
            if child is None: colors[current] = 2; stack.pop(); trail.pop(); continue
            if colors.get(child) == 1:
                cycle = trail[trail.index(child):] + [child]
                if cycle not in cycles: cycles.append(cycle)
            elif not colors.get(child):
                colors[child] = 1; trail.append(child); stack.append((child, iter(sorted(dependencies[child]))))
    gaps.sort(key=lambda g: (g['kind'], g['name'], g['source'], g['relationship'], g['status']))
    missing = [g for g in gaps if g['status'] in {'missing', 'ambiguous', 'source_conflict', 'bounded_discovery'}]
    blocked = not root_nodes or any(g['status'] in {'missing', 'ambiguous', 'source_conflict', 'bounded_discovery', 'unresolved_parser'} for g in gaps)
    status = 'BLOCKED' if blocked else 'PARTIAL' if gaps else 'COMPLETE'
    asset_kinds = [('batch_cobol', 'Batch COBOL programs', 'program'), ('jcl_jobs', 'Jobs', 'job'),
                   ('jcl_procs', 'PROCs', 'proc'), ('copybooks', 'Copybooks', 'copybook'),
                   ('cics_screens', 'CICS screens', 'bms_map'),
                   ('db2_tables', 'Db2 tables', 'db2_table'), ('ca7_schedules', 'CA7 schedules', 'ca7_definition'),
                   ('mq', 'MQ interfaces', 'mq_interface')]
    process_assets = []
    for key, label, kind in asset_kinds:
        observed = len({n['id'] for n in nodes.values() if n['kind'] == kind and n['selected'] and n['resolution'] in {'local_source', 'read_only_metadata'}})
        inventory = len({n['id'] for n in nodes.values() if n['kind'] == kind and n['resolution'] == 'local_source'})
        relevant_gaps = [g for g in gaps if g['kind'] == kind]
        # A parser finding no CICS/CA7/MQ definitions cannot prove those domains empty.
        known = status == 'COMPLETE' and kind in {'program', 'job', 'proc', 'copybook'} and not relevant_gaps
        process_assets.append({'kind': key, 'label': label, 'observed_count': observed,
                               'local_inventory_count': inventory, 'count': observed if known else 'Unknown',
                               'status': 'OBSERVED_STATIC_CLOSURE' if known else 'UNVERIFIED',
                               'basis': 'selected source references and declarations', 'gaps': len(relevant_gaps)})
    return {'schema_version': 1, 'stage': 'LINEAGE_MAPPING',
            'nodes': sorted(nodes.values(), key=lambda n: n['id']),
            'edges': sorted(edges, key=lambda e: (e['source'], e['target'], e['kind'], str(e['evidence'][0].get('line')))),
            'scope': {'strategy': 'transaction_led_transitive_closure' if manifest.get('transactions') else 'job_led_transitive_closure', 'root_transactions': [t['id'] for t in manifest.get('transactions',[])], 'root_jobs': [j['name'] for j in manifest.get('jobs', [])],
                      'selected_files': selected_paths, 'retained_files': inventory_paths,
                      'excluded_files': [{'path': p, 'reason': 'Not reached from selected jobs under the bounded static parser; retained for inventory and review'} for p in inventory_paths if p not in selected_paths],
                      'local_repository_checked': True, 'original_file_count': len(original_paths),
                      'retained_file_count': len(inventory_paths), 'discovered_file_count': len(sources) - len(original_paths),
                      'selected_file_count': len(selected_paths)},
            'closure': {'status': status, 'complete': status == 'COMPLETE', 'gaps': gaps,
                        'basis': 'bounded_static_source_mapping', 'estate_complete': False,
                        'input_data_readiness': 'Unknown', 'cycles': sorted(cycles)},
            'missing_objects': missing, 'unresolved_references': gaps, 'process_assets': process_assets,
            'read_only_lookups': lookups, 'source_snapshots': sorted(snapshots, key=lambda s: s['path']),
            'application_input_locations': location_facts,
            'parser': {'name': 'bounded-mainframe-static-lineage', 'version': 1, 'limits': PARSER_LIMITS,
                       'indexed_files': len(parsed), 'max_read_only_lookups': MAX_LOOKUPS,
                       'no_llm': True, 'observed_legacy_parity': False},
            'source_snapshot_hash': sha(encode({p: {'source_hash': sha(t), 'provenance': provenance.get(p, {'origin': 'local_repository_export', 'path': p})}
                                               for p, t in sorted(sources.items())}))}
