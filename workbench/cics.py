"""Source-bound BMS character layouts and their bounded Python replacement.

This adapter implements layout/field behavior, not native CICS controller,
terminal I/O, authentication, transaction or persistence semantics. Source
expectations are evaluated independently before the emitted target executes.
"""
import ast
import bisect
from copy import deepcopy
import random
import re

from .domain import ValidationError, encode, require, sha

PROFILE = 'BMS_CHARACTER_LAYOUT_V1'
NAME = r'[A-Z@$#][A-Z0-9@$#_-]{0,29}'
ATTRIBUTES = {'ASKIP', 'PROT', 'UNPROT', 'NORM', 'BRT', 'IC'}
LIMITATIONS = [
    'Character layout and field presentation only; SEND/RECEIVE, symbolic map buffers and CICS controller behavior are unverified.',
    'Printable ASCII local input is an explicit replacement contract, not verified native CCSID or 3270 data-stream parity.',
    'Native AID/MAPFAIL, navigation, COMMAREA/channels, authorization, persistence and recovery require source-supported adapters.',
]


def _gap(kind, message, path, first, last, **extra):
    return {'kind': kind, 'message': message, 'source_path': path, 'path': path,
            'start_line': first, 'end_line': last,
            'lines': list(range(first, last + 1)), **extra}


def _parts(text):
    """Split assembler operands without interpreting strings or expressions."""
    parts = []; start = 0; depth = 0; quote = None; i = 0
    while i < len(text):
        char = text[i]
        if quote:
            if char == quote:
                if i + 1 < len(text) and text[i + 1] == quote:
                    i += 2; continue
                quote = None
        elif char in "'\"": quote = char
        elif char == '(': depth += 1
        elif char == ')':
            depth -= 1; require(depth >= 0, 'Unbalanced BMS operand parentheses')
        elif char == ',' and depth == 0:
            parts.append(text[start:i].strip()); start = i + 1
        i += 1
    require(not quote and depth == 0, 'Unclosed BMS quoted literal or operand list')
    if text[start:].strip(): parts.append(text[start:].strip())
    require(all(parts), 'Empty BMS operand')
    return parts


def _options(text):
    result = {}
    for part in _parts(text):
        match = re.fullmatch(r'([A-Z][A-Z0-9]*)\s*=\s*(.+)', part, re.I)
        require(match is not None, 'BMS operands must have explicit KEY=literal values')
        key = match[1].upper(); require(key not in result, 'Duplicate BMS operand ' + key)
        result[key] = match[2].strip()
    return result


def _number(value, label, low=1, high=256):
    require(isinstance(value, str) and re.fullmatch(r'\d{1,6}', value), label + ' needs a bounded literal integer')
    result = int(value); require(low <= result <= high, label + ' is outside the supported range')
    return result


def _pair(value, label):
    match = re.fullmatch(r'\(\s*(\d{1,6})\s*,\s*(\d{1,6})\s*\)', value or '')
    require(match is not None, label + ' needs an explicit (row,column) pair')
    return _number(match[1], label + ' row', high=240), _number(match[2], label + ' column', high=240)


def _literal(value):
    require(isinstance(value, str) and re.fullmatch(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"", value), 'INITIAL must be a quoted character literal')
    result = value[1:-1].replace(value[0] * 2, value[0])
    require(all(32 <= ord(char) <= 126 for char in result), 'INITIAL requires printable ASCII; native encoding needs a separate adapter')
    return result


def _records(text):
    """Retain physical spans; accept explicit free-format comma continuations.

    Fixed-format continuation columns, sequence fields, assembler expressions
    and macro substitutions are intentionally not normalized into support.
    """
    lines = text.splitlines(); records = []; pending = None
    for number, raw in enumerate(lines, 1):
        if not raw.strip() or raw.lstrip().startswith('*'):
            if pending:
                pending['errors'].append('Comment/blank interrupts an explicit BMS continuation')
                records.append(pending); pending = None
            continue
        body = raw.strip(); errors = []
        if len(raw) > 71 and raw[71:].strip():
            errors.append('Fixed-format continuation/sequence columns need an exact assembler source-format adapter')
        # Free-format exports often put a literal X after a trailing comma.
        marker = re.search(r',\s+X\s*$', body, re.I)
        if marker: body = body[:marker.start() + 1]
        continued = body.endswith(',')
        if pending:
            if re.match(r'(?:(?:' + NAME + r')\s+)?DFHM(?:SD|DI|DF)\b|END\b', body, re.I):
                pending['errors'].append('BMS continuation ends before the next macro')
                records.append(pending); pending = None
            else:
                pending['text'] += body; pending['end_line'] = number
                pending['errors'] += errors
                if not continued: records.append(pending); pending = None
                continue
        record = {'text': body, 'start_line': number, 'end_line': number, 'errors': errors}
        if continued: pending = record
        else: records.append(record)
    if pending:
        pending['errors'].append('Unterminated BMS continuation'); records.append(pending)
    return records


def _unit(kind, path, source_hash, record, *, mapset=None, screen=None,
          field=None, operation=None, program=None, required=True,
          support='unsupported', diagnostics=(), description='', replacement='', component=''):
    return {'kind': kind, 'program': program, 'source_path': path, 'source_hash': source_hash,
            'start_line': record['start_line'], 'end_line': record['end_line'],
            'mapset': mapset, 'map': screen, 'screen': screen, 'field': field,
            'operation': operation, 'component': component, 'required': required,
            'support': support, 'diagnostics': list(diagnostics),
            'description': description, 'replacement': replacement}


def parse_bms(path, text):
    """Parse a strict, literal BMS profile; unknown source stays a named gap."""
    source_hash = sha(text); units = []; screens = []; gaps = []
    mapset = None; current = None; closed = False; final_seen = False; end_seen = False
    map_names = set(); field_names = set(); mapset_options = {}; occupied = set()
    for record in _records(text):
        raw = record['text']; first = record['start_line']; last = record['end_line']
        errors = list(record['errors']); diagnostics = []
        match = re.fullmatch(r'(?:((' + NAME + r'))\s+)?(DFHMSD|DFHMDI|DFHMDF)\b\s*(.*)', raw, re.I)
        # END is an assembler directive, never an executable target capability.
        if re.fullmatch(r'END(?:\s+' + NAME + r')?', raw, re.I):
            if not final_seen: errors.append('END precedes DFHMSD TYPE=FINAL')
            if end_seen: errors.append('Repeated END directive')
            end_seen = True
            if errors:
                diagnostics = [_gap('bms_structure_gap', message, path, first, last) for message in errors]
                gaps.extend(diagnostics)
            units.append(_unit('screen_definition', path, source_hash, record, mapset=mapset,
                               support='unsupported' if errors else 'layout_supported', diagnostics=diagnostics,
                               description='BMS assembler END directive', component='assembler_end',
                               replacement='No executable statement; retain source and close the literal map layout.'))
            continue
        if not match:
            diagnostic = _gap('bms_unparsed_source', 'Unparsed BMS source requires a reviewed assembler/macro adapter: ' + raw[:160], path, first, last)
            gaps.append(diagnostic)
            units.append(_unit('screen_definition', path, source_hash, record, mapset=mapset,
                               diagnostics=[diagnostic], description='Unparsed BMS source', component='unparsed',
                               replacement='No verified replacement; retain the exact macro/source obligation.'))
            continue
        label = (match[1] or '').upper() or None; macro = match[3].upper()
        try: options = _options(match[4])
        except ValidationError as exc: options = {}; errors.append(str(exc))
        if end_seen: errors.append('BMS macro appears after END')
        if macro == 'DFHMSD':
            typ = options.get('TYPE', '').upper()
            if typ == 'FINAL':
                if set(options) != {'TYPE'}: errors.append('TYPE=FINAL has unsupported extra operands')
                if label: errors.append('TYPE=FINAL must not redeclare a mapset label in this profile')
                if not mapset or not screens or final_seen: errors.append('Missing/repeated mapset or map before TYPE=FINAL')
                final_seen = True; closed = True; current = None
                description = 'BMS mapset completion'; component = 'mapset_final'
            else:
                if mapset: errors.append('Multiple mapsets in one export need explicit disambiguation')
                if not label or len(label)>7: errors.append('DFHMSD requires a literal mapset label of at most seven characters')
                mapset = label; mapset_options = options
                allowed = {'TYPE', 'LANG', 'MODE', 'STORAGE', 'TIOAPFX'}
                if set(options) - allowed: errors.append('Unsupported DFHMSD operands: ' + ', '.join(sorted(set(options) - allowed)))
                if typ not in {'MAP', 'DSECT'}: errors.append('DFHMSD TYPE must be literal MAP or DSECT; macro substitutions are unverified')
                if options.get('LANG', '').upper() not in {'COBOL','COBOL2'}: errors.append('LANG=COBOL/COBOL2 must be explicit; native symbolic language defaults are not invented')
                if options.get('MODE', 'INOUT').upper() not in {'IN', 'OUT', 'INOUT'}: errors.append('Unsupported mapset MODE')
                if options.get('STORAGE', 'AUTO').upper() != 'AUTO': errors.append('Non-AUTO storage requires native lifetime/buffer semantics')
                if options.get('TIOAPFX', 'YES').upper() != 'YES': errors.append('Non-YES TIOAPFX requires a native symbolic layout adapter')
                description = 'Mapset ' + str(label) + ' character layout'; component = 'mapset'
            diagnostics = [_gap('bms_structure_gap', message, path, first, last, mapset=mapset) for message in errors]
            gaps.extend(diagnostics)
            units.append(_unit('screen_definition', path, source_hash, record, mapset=mapset,
                               support='unsupported' if errors else 'layout_supported', diagnostics=diagnostics,
                               description=description, component=component,
                               replacement='Python screen contract binds the exact source mapset; native generated symbolic buffers remain unverified.'))
        elif macro == 'DFHMDI':
            if not mapset or closed: errors.append('DFHMDI requires an open literal DFHMSD mapset')
            if not label or len(label)>7 or label in map_names: errors.append('Missing/duplicate map label or map name longer than seven characters')
            map_names.add(label)
            if set(options) - {'SIZE', 'LINE', 'COLUMN'}: errors.append('Unsupported DFHMDI operands: ' + ', '.join(sorted(set(options) - {'SIZE', 'LINE', 'COLUMN'})))
            try:
                rows, columns = _pair(options.get('SIZE'), 'DFHMDI SIZE')
                require(rows * columns <= 65536, 'Map dimensions exceed the layout bound')
                require(_number(options.get('LINE', '1'), 'LINE') == 1 and _number(options.get('COLUMN', '1'), 'COLUMN') == 1,
                        'Non-origin map placement requires verified terminal partition/origin semantics')
            except ValidationError as exc: rows = columns = None; errors.append(str(exc))
            diagnostics = [_gap('bms_structure_gap', message, path, first, last, mapset=mapset, map=label) for message in errors]
            gaps.extend(diagnostics)
            current = {'id': 'SCREEN_' + sha(encode([path, source_hash, mapset, label, first]))[:24],
                       'mapset': mapset, 'map': label, 'source_path': path, 'source_hash': source_hash,
                       'start_line': first, 'end_line': last, 'rows': rows, 'columns': columns,
                       'fields': [], 'owners': [], 'support': 'unsupported' if errors else 'layout_supported',
                       'gaps': list(diagnostics), 'profile': PROFILE, 'mapset_options': mapset_options}
            screens.append(current); occupied = set()
            units.append(_unit('screen_definition', path, source_hash, record, mapset=mapset, screen=label,
                               support=current['support'], diagnostics=diagnostics, component='map',
                               description='Screen ' + str(mapset) + '/' + str(label) + ' dimensions and field order',
                               replacement='Python/FastAPI screen contract preserves dimensions, source field order and positions; controller flow remains separate.'))
        else:
            if current is None: errors.append('DFHMDF requires an open DFHMDI map')
            elif len(current['fields'])>=1023: errors.append('BMS layout adapter capacity is 1023 total fields per screen; excess definitions remain unverified')
            if label and (not re.fullmatch(r'[A-Z][A-Z0-9-]{0,28}',label) or label in field_names):
                errors.append('COBOL BMS fields need unique alphabetic names of at most 29 characters using supported COBOL characters')
            if label:
                field_names.add(label)
                if len(field_names)>1023: errors.append('COBOL BMS mapset exceeds the supported 1023 named-field capacity')
            allowed = {'POS', 'LENGTH', 'ATTRB', 'INITIAL'}
            if set(options) - allowed: errors.append('Unsupported DFHMDF operands: ' + ', '.join(sorted(set(options) - allowed)))
            attrs = ['ASKIP', 'NORM']; width = None; position = None; initial = ''; editable = False
            try:
                width = _number(options.get('LENGTH', ''), 'DFHMDF LENGTH', low=0 if label is None else 1)
                require(current is not None and current['rows'] is not None, 'Field requires valid map dimensions')
                if options.get('POS', '').startswith('('):
                    row, column = _pair(options.get('POS'), 'DFHMDF POS')
                    require(row <= current['rows'] and column <= current['columns'], 'Field attribute position lies outside its map')
                    position = (row - 1) * current['columns'] + column - 1
                else: position = _number(options.get('POS', ''), 'DFHMDF POS', low=0, high=65535)
                require(position + width < current['rows'] * current['columns'], 'Field data exceeds the map boundary')
                if 'ATTRB' in options:
                    value = options['ATTRB'].upper()
                    attrs = _parts(value[1:-1]) if value.startswith('(') and value.endswith(')') else [value]
                    require(attrs and len(attrs) == len(set(attrs)), 'Empty or duplicate field attributes')
                    require(set(attrs) <= ATTRIBUTES, 'Unsupported field attributes: ' + ', '.join(sorted(set(attrs) - ATTRIBUTES)))
                    require(len(set(attrs) & {'ASKIP', 'PROT', 'UNPROT'}) <= 1, 'Conflicting protection attributes')
                    require(len(set(attrs) & {'NORM', 'BRT'}) <= 1, 'Conflicting intensity attributes')
                    # IBM DFHMDF has two different documented defaults:
                    # omitted ATTRB => ASKIP,NORM; any explicit attribute =>
                    # UNPROT,NORM, with each specified category overriding it.
                    if not set(attrs) & {'ASKIP', 'PROT', 'UNPROT'}: attrs.insert(0,'UNPROT')
                    if not set(attrs) & {'NORM', 'BRT'}: attrs.append('NORM')
                editable = 'UNPROT' in attrs
                require('IC' not in attrs or editable, 'Cursor on a protected field requires exact terminal navigation semantics')
                require(not editable or label is not None, 'Unnamed editable fields need a symbolic input-binding adapter')
                require(not editable or current['mapset_options'].get('MODE', 'INOUT').upper() != 'OUT', 'Editable field conflicts with an OUT-only mapset')
                if 'INITIAL' in options: initial = _literal(options['INITIAL'])
                require(len(initial) <= width, 'INITIAL exceeds LENGTH')
                require(not any(item['name'] == label for item in current['fields']) if label else True, 'Duplicate field label')
                cells = set(range(position, position + width + 1))
                require(not occupied & cells, 'Overlapping field attributes/data need a verified 3270 overlap/delimiter adapter')
                occupied.update(cells)
            except ValidationError as exc: errors.append(str(exc))
            diagnostics = [_gap('bms_field_gap', message, path, first, last, mapset=mapset,
                                map=(current or {}).get('map'), field=label) for message in errors]
            gaps.extend(diagnostics)
            field_id = label or 'STATIC_' + sha(encode([path, source_hash, first, last]))[:16]
            field = {'id': field_id, 'name': label, 'width': width, 'attribute_offset': position,
                     'attributes': attrs, 'editable': editable, 'initial': initial.ljust(width or 0),
                     'source_path': path, 'source_hash': source_hash, 'start_line': first, 'end_line': last,
                     'required': editable or label is not None, 'support': 'unsupported' if errors else 'layout_supported'}
            if current:
                current['fields'].append(field); current['end_line'] = last; current['gaps'].extend(diagnostics)
                if errors: current['support'] = 'unsupported'
            units.append(_unit('screen_field', path, source_hash, record, mapset=mapset,
                               screen=(current or {}).get('map'), field=field_id, required=field['required'],
                               support=field['support'], diagnostics=diagnostics, component='field',
                               description=('Input' if editable else 'Display') + ' field ' + field_id + ', LENGTH=' + str(width) + ', ATTRB=' + ','.join(attrs),
                               replacement='Python fixed-width character validation and source-owned position/protection/default presentation; native symbolic-map I/O remains unverified.'))
    if not final_seen or not end_seen:
        diagnostic = _gap('bms_structure_gap', 'Complete export requires DFHMSD TYPE=FINAL and END; do not infer missing source', path, max(1, len(text.splitlines())), max(1, len(text.splitlines())))
        gaps.append(diagnostic)
    # A file-level parsing failure cannot give any map in that file full layout credit.
    if gaps:
        for screen in screens:
            screen['support'] = 'unsupported'
            screen['gaps'] = [gap for gap in gaps if gap not in screen['gaps']] + screen['gaps']
    return {'units': units, 'screens': screens, 'gaps': gaps}


def _masked_cobol(text):
    """Mask literals/comments without changing physical-line positions."""
    from .source import normalized_lines
    raw = '\n'.join(line if kind == 'code' else '' for kind, line in normalized_lines(text))
    chars = list(raw); quote = None; i = 0
    while i < len(chars):
        char = chars[i]
        if quote:
            if char == quote:
                if i + 1 < len(chars) and chars[i + 1] == quote:
                    chars[i] = chars[i + 1] = ' '; i += 2; continue
                quote = None
            if char != '\n': chars[i] = ' '
        elif char in "'\"": quote = char; chars[i] = ' '
        i += 1
    return raw, ''.join(chars)


def _actions(path, text, program):
    raw, masked = _masked_cobol(text)
    offsets = [-1] + [i for i, char in enumerate(raw) if char == '\n']
    units = []; gaps = []
    starts = list(re.finditer(r'\bEXEC\s+CICS\b', masked, re.I))
    for index, begin in enumerate(starts):
        boundary = starts[index + 1].start() if index + 1 < len(starts) else len(masked)
        terminal = re.search(r'\bEND-EXEC\b', masked[begin.end():boundary], re.I)
        finish = begin.end() + terminal.end() if terminal else boundary
        while finish > begin.start() and raw[finish - 1].isspace(): finish -= 1
        first = bisect.bisect_left(offsets, begin.start())
        last = bisect.bisect_left(offsets, max(begin.start(), finish - 1))
        command = raw[begin.start():finish]; command_masked = masked[begin.start():finish]
        operation_match = re.match(r'EXEC\s+CICS\s+([A-Z][A-Z0-9-]*)', command_masked, re.I)
        operation = operation_match[1].upper() if operation_match else 'UNKNOWN'
        suffix = command_masked[operation_match.end():] if operation_match else ''
        form_match = re.match(r'\s*(MAP|TEXT|CONTROL)(?![A-Z0-9-])', suffix, re.I)
        form = form_match[1].upper() if operation in {'SEND', 'RECEIVE'} and form_match else None
        # Operand names inside FROM/INTO data-area parentheses are not command
        # options. Keep offsets for literal extraction while exposing top-level keys.
        top_level = list(command_masked); depth = 0
        for offset, char in enumerate(command_masked):
            if depth: top_level[offset] = ' '
            if char == '(': depth += 1
            elif char == ')': depth = max(0, depth - 1)
        option_text = ''.join(top_level)
        def binding(name):
            tokens = list(re.finditer(r'(?<![A-Z0-9@$#_-])' + name + r'(?![A-Z0-9@$#_-])', option_text, re.I))
            keywords = list(re.finditer(r'(?<![A-Z0-9@$#_-])' + name + r'\s*\(', option_text, re.I))
            if len(tokens) != 1 or len(keywords) != 1: return None
            keyword = keywords[0]
            match = re.match(r"\s*(['\"])(" + NAME + r")\1\s*\)", command[keyword.end():], re.I)
            return match[2].upper() if match else None
        map_name = binding('MAP') if form == 'MAP' else None
        mapset_operand = re.search(r'(?<![A-Z0-9@$#_-])MAPSET(?![A-Z0-9@$#_-])', option_text, re.I) if form == 'MAP' else None
        mapset = binding('MAPSET') if form == 'MAP' else None
        mapset_binding_basis = 'explicit_literal' if mapset else 'unresolved' if form == 'MAP' else None
        # IBM SEND/RECEIVE MAP defaults an omitted MAPSET to the literal MAP
        # name. An explicit dynamic or malformed MAPSET never takes that default.
        if form == 'MAP' and map_name and mapset_operand is None:
            mapset = map_name; mapset_binding_basis = 'ibm_default_map_name'
        display_operation = operation + (' ' + form if form else '')
        diagnostic = _gap('cics_controller_gap', 'CICS ' + display_operation + ': native controller/buffer/AID/error/session/transaction behavior has no verified Python/FastAPI replacement; layout conversion alone does not implement this command.', path, first, last, program=program, operation=operation, form=form, mapset=mapset, map=map_name)
        diagnostics = [diagnostic]
        if not terminal:
            diagnostics.append(_gap('cics_command_gap', 'EXEC CICS ' + display_operation + ' has no END-EXEC before the next command or end of the complete export', path, first, last, program=program))
        if form == 'MAP' and (not mapset or not map_name):
            diagnostics.append(_gap('cics_binding_gap', 'CICS ' + display_operation + ' requires a literal MAP and an explicit literal MAPSET or the IBM documented omitted-MAPSET default; dynamic/malformed bindings remain unverified.', path, first, last, program=program, operation=operation))
        buffer_name = None
        if form == 'MAP':
            operand = 'INTO' if operation == 'RECEIVE' else 'FROM'
            keyword = re.search(r'\b' + operand + r'\s*\(', command_masked, re.I)
            if keyword:
                value = re.match(r'\s*(' + NAME + r')\s*\)', command[keyword.end():], re.I)
                buffer_name = value[1].upper() if value else None
            diagnostics.append(_gap('cics_buffer_gap', 'CICS ' + display_operation + ' ' + operand + '(' + (buffer_name or 'unresolved') + '): original symbolic-map COPY/declaration, length/attribute flags, input/output overlay and exact buffer semantics are not implemented by the character layout adapter.', path, first, last, program=program, operation=operation, buffer=buffer_name, mapset=mapset, map=map_name))
        gaps.extend(diagnostics)
        unit = _unit('screen_action', path, sha(text), {'start_line': first, 'end_line': last},
                     mapset=mapset, screen=map_name, operation=operation, program=program,
                     support='unverified_controller', diagnostics=diagnostics, component='controller',
                     description='CICS ' + display_operation + (' ' + str(mapset) + '/' + str(map_name) if map_name else '') + ' controller action',
                     replacement='Unverified controller obligation: implement source-owned symbolic buffers, AID/RESP/MAPFAIL/state/effects and test the actual FastAPI replacement before conversion credit.')
        unit['form'] = form; unit['buffer'] = buffer_name
        unit['mapset_binding_basis'] = mapset_binding_basis
        if mapset_binding_basis == 'ibm_default_map_name':
            unit['mapset_default_reference'] = ('https://www.ibm.com/docs/en/cics-ts/5.5.0?topic=summary-receive-map' if operation == 'RECEIVE' else 'https://www.ibm.com/docs/en/cics-ts/6.x?topic=summary-send-map')
        # Multiple commands sharing a physical line cannot have independently
        # selectable source-line spans. Retain their facts in one explicit unit.
        if units and unit['start_line'] <= units[-1]['end_line']:
            previous = units[-1]
            bindings = previous.get('bindings', [{'mapset': previous['mapset'], 'map': previous['map'], 'operation': previous['operation'], 'form': previous.get('form'), 'mapset_binding_basis': previous.get('mapset_binding_basis')}])
            bindings.append({'mapset': mapset, 'map': map_name, 'operation': operation, 'form': form, 'mapset_binding_basis': mapset_binding_basis})
            previous.update({'end_line': last, 'operation': 'MULTIPLE', 'form': None, 'buffer': None,
                             'mapset': mapset if previous['mapset'] == mapset else None,
                             'map': map_name if previous['map'] == map_name else None,
                             'screen': map_name if previous['screen'] == map_name else None,
                             'description': 'Multiple CICS controller commands share source lines; preserve all command diagnostics together.',
                             'bindings': bindings})
            previous['diagnostics'].extend(diagnostics)
        else: units.append(unit)
    return units, gaps


def analyze_cics(files, manifest, programs, classifications=None):
    """Gather complete source-owned screen units; never assert native parity."""
    require(manifest.get('cics_contract_version') == 1, 'CICS analysis requires its frozen new-intake contract')
    selected = set(manifest.get('lineage_scope', files)); units = []; screens = []; gaps = []
    for path, text in sorted(files.items()):
        kind = (classifications or {}).get(path, {}).get('kind')
        if path not in selected or (kind != 'bms_map' if classifications is not None else not path.lower().endswith('.bms')): continue
        parsed = parse_bms(path, text); units += parsed['units']; screens += parsed['screens']; gaps += parsed['gaps']
    actions = []
    for name, program in sorted(programs.items()):
        own, problems = _actions(program['path'], program['source_text'], name)
        actions += own; units += own; gaps += problems
    for screen in screens:
        screen['owners'] = sorted({tx['program'] for tx in manifest.get('transactions', [])
                                   if tx.get('mapset') == screen['mapset'] and tx.get('map') == screen['map']} |
                                  {unit['program'] for unit in actions if any(
                                       ref.get('mapset') == screen['mapset'] and ref.get('map') == screen['map']
                                       for ref in unit['diagnostics'])})
        # Native controller/buffer behavior is not implemented, so a named
        # output field remains required even when its individual name is not
        # referenced: FROM(MAPO) can transfer the whole symbolic map. Only
        # unnamed constant presentation fields are safely optional.
    # Bind each real MAP command to exactly one retained source definition.
    for unit in actions:
        for binding in unit.get('bindings', [unit]):
            if binding.get('form') != 'MAP' or not binding.get('mapset') or not binding.get('map'): continue
            matches = [screen for screen in screens if (screen['mapset'], screen['map']) == (binding['mapset'], binding['map'])]
            if len(matches) != 1:
                diagnostic = _gap('cics_binding_gap', 'CICS map binding is missing or ambiguous in the retained export: ' + binding['mapset'] + '/' + binding['map'],
                                  unit['source_path'], unit['start_line'], unit['end_line'], program=unit['program'], mapset=binding['mapset'], map=binding['map'])
                gaps.append(diagnostic); unit['diagnostics'].append(diagnostic)
    pairs = {}
    for screen in screens: pairs.setdefault((screen['mapset'], screen['map']), []).append(screen)
    for pair, definitions in pairs.items():
        if len(definitions) > 1:
            for screen in definitions:
                diagnostic = _gap('bms_definition_ambiguity', 'Multiple retained BMS definitions claim ' + str(pair[0]) + '/' + str(pair[1]) + '; resolve the exact deployed source version before layout credit.',
                                  screen['source_path'], screen['start_line'], screen['end_line'], mapset=pair[0], map=pair[1])
                screen['support'] = 'unsupported'; screen['gaps'].append(diagnostic); gaps.append(diagnostic)
    return {'schema_version': 1, 'profile': PROFILE, 'units': units, 'screens': screens,
            'gaps': gaps, 'limitations': list(LIMITATIONS), 'native_cics_verified': False}


def selected_screens(analysis):
    """Derive presentation scope from canonical selections; preserve descriptors."""
    require(analysis.get('cics_contract_version') == 1, 'Screen scope requires its frozen contract')
    result = deepcopy(analysis.get('cics', {}).get('screens', []))
    excluded = (analysis.get('requirements') or {}).get('excluded_units', [])
    for screen in result:
        dependencies = [unit for unit in excluded if unit.get('required', True) and (
            unit.get('source_path') == screen['source_path'] and unit.get('kind') == 'screen_definition'
            and (not unit.get('map') or unit.get('map') == screen['map'])
            or unit.get('kind') == 'screen_action' and unit.get('program') in screen['owners'])]
        if dependencies:
            screen['support'] = 'unsupported'
            screen['gaps'] += [_gap('requirements_dependency', 'Not converted because selected No in requirements. Required BMS definition/controller dependencies cannot be waived by layout generation.',
                                   unit['source_path'], unit['start_line'], unit['end_line']) for unit in dependencies]
        omitted = [unit for unit in excluded if unit.get('source_path') == screen['source_path']
                   and unit.get('kind') == 'screen_field'
                   and any(field['start_line'] == unit['start_line'] and field['end_line'] == unit['end_line'] for field in screen['fields'])]
        forbidden = [unit for unit in omitted if unit.get('required', True) or unit.get('support') != 'layout_supported']
        if forbidden:
            screen['support'] = 'unsupported'
            screen['gaps'] += [_gap('requirements_dependency', 'Not converted because selected No in requirements. Required or unsupported BMS fields cannot be removed without a verified controller/layout redesign.',
                                   unit['source_path'], unit['start_line'], unit['end_line']) for unit in forbidden]
        screen['omitted_fields'] = [field for field in screen['fields'] if any(field['start_line'] == unit['start_line'] for unit in omitted)]
        screen['fields'] = [field for field in screen['fields'] if not any(field['start_line'] == unit['start_line'] for unit in omitted)]
        if omitted: screen['requirements_hash'] = sha(encode((analysis.get('requirements') or {}).get('selection', {})))
    return result


def validate_screen(screen):
    require(isinstance(screen, dict) and screen.get('profile') == PROFILE and screen.get('support') == 'layout_supported' and not screen.get('gaps'), 'Unsupported screen cannot receive executable layout credit')
    require(isinstance(screen.get('source_hash'), str) and re.fullmatch(r'[a-f0-9]{64}', screen['source_hash']), 'Screen source hash is invalid')
    require(type(screen.get('rows')) is int and type(screen.get('columns')) is int and 1 <= screen['rows'] <= 240 and 1 <= screen['columns'] <= 240, 'Invalid screen dimensions')
    require(all(isinstance(screen.get(key),str) and re.fullmatch(r'[A-Z@$#][A-Z0-9@$#_-]{0,6}',screen[key]) for key in ('mapset','map')), 'Invalid literal mapset/map identity')
    require(isinstance(screen.get('fields'), list) and len(screen['fields']) <= 1023, 'Screen fields exceed the supported bound')
    names = set(); cells = set()
    for field in screen['fields']:
        require(isinstance(field, dict) and isinstance(field.get('id'), str) and field['id'] not in names, 'Duplicate or invalid screen field identity')
        names.add(field['id'])
        require(field.get('support') == 'layout_supported' and type(field.get('width')) is int and (1 if field.get('name') else 0) <= field['width'] <= 256, 'Invalid screen field width/support')
        require(field.get('name') is None or isinstance(field['name'],str) and bool(re.fullmatch(r'[A-Z][A-Z0-9-]{0,28}',field['name'])) and field['id']==field['name'], 'Invalid COBOL field name/binding')
        require(type(field.get('required')) is bool and (not field.get('name') or field['required']), 'Native named field dependencies cannot be waived by a presentation flag')
        require(type(field.get('attribute_offset')) is int and 0 <= field['attribute_offset'] and field['attribute_offset'] + field['width'] < screen['rows'] * screen['columns'], 'Screen field lies outside its layout')
        occupied = set(range(field['attribute_offset'], field['attribute_offset'] + field['width'] + 1)); require(not occupied & cells, 'Overlapping screen fields'); cells.update(occupied)
        require(type(field.get('editable')) is bool and (not field['editable'] or bool(field.get('name'))), 'Invalid field editability/binding')
        attributes=field.get('attributes')
        require(isinstance(attributes,list) and all(isinstance(value,str) for value in attributes)
                and len(attributes)==len(set(attributes)) and set(attributes)<=ATTRIBUTES
                and len(set(attributes)&{'ASKIP','PROT','UNPROT'})==1
                and len(set(attributes)&{'NORM','BRT'})==1
                and ('UNPROT' in attributes)==field['editable']
                and ('IC' not in attributes or field['editable']), 'Invalid screen field attributes')
        require(type(field.get('initial')) is str and len(field['initial']) == field['width'] and all(32 <= ord(c) <= 126 for c in field['initial']), 'Invalid screen field default')
    return screen


def _input_errors(screen, values):
    if type(values) is not dict: return ['values must be an object']
    expected = sorted(field['id'] for field in screen['fields'] if field['editable'])
    errors = []
    if set(values) != set(expected): errors.append('field set differs from selected BMS input layout')
    for field in sorted((field for field in screen['fields'] if field['editable']), key=lambda item: item['id']):
        value = values.get(field['id'])
        if type(value) is not str or len(value) != field['width'] or any(ord(c) < 32 or ord(c) > 126 for c in value):
            errors.append(field['id'] + ': invalid fixed-width printable ASCII characters')
    return errors


def screen_reference(screen, values):
    """Independently interpret BMS field position/default/protection semantics."""
    validate_screen(screen); errors = _input_errors(screen, values)
    if errors: return {'input_status': 'REJECT_INPUT', 'errors': errors, 'return_code': None}
    fields = []
    for field in screen['fields']:
        offset = field['attribute_offset'] + 1
        fields.append({'id': field['id'], 'name': field['name'], 'width': field['width'],
                       'row': offset // screen['columns'] + 1, 'column': offset % screen['columns'] + 1,
                       'attribute_offset': field['attribute_offset'], 'editable': field['editable'],
                       'intensity': 'bright' if 'BRT' in field['attributes'] else 'normal',
                       'cursor': 'IC' in field['attributes'],
                       'value': values[field['id']] if field['editable'] else field['initial']})
    cursor = next((field['id'] for field in reversed(fields) if field['cursor']), None)
    return {'input_status': 'ACCEPT_INPUT', 'screen': {'mapset': screen['mapset'], 'map': screen['map'],
            'rows': screen['rows'], 'columns': screen['columns'], 'fields': fields, 'cursor_field': cursor}, 'return_code': 0}


def emit_screen(screen):
    """Emit auditable local screen code from the source IR, never a model plan."""
    validate_screen(screen)
    lines = ['# BMS source SHA256 ' + screen['source_hash'], '# Profile ' + PROFILE,
             '# SOURCE_DERIVED_EXPECTED; native CICS controller behavior remains unverified.',
             'def run_screen(values):', '    if type(values) is not dict:',
             "        return {'input_status': 'REJECT_INPUT', 'errors': ['values must be an object'], 'return_code': None}",
             '    errors = []']
    inputs = sorted((field for field in screen['fields'] if field['editable']), key=lambda item: item['id'])
    shape = 'len(values) != ' + str(len(inputs))
    for field in inputs: shape += ' or ' + repr(field['id']) + ' not in values'
    lines += ['    if ' + shape + ':', "        errors.append('field set differs from selected BMS input layout')"]
    for field in inputs:
        expression = 'values.get(' + repr(field['id']) + ')'
        lines += ['    if type(' + expression + ') is not str or len(' + expression + ') != ' + str(field['width']) + ' or any(ord(c) < 32 or ord(c) > 126 for c in ' + expression + '):',
                  '        errors.append(' + repr(field['id'] + ': invalid fixed-width printable ASCII characters') + ')']
    lines += ['    if errors:', "        return {'input_status': 'REJECT_INPUT', 'errors': errors, 'return_code': None}", '    fields = []']
    for field in screen['fields']:
        offset = field['attribute_offset'] + 1
        item = {'id': field['id'], 'name': field['name'], 'width': field['width'],
                'row': offset // screen['columns'] + 1, 'column': offset % screen['columns'] + 1,
                'attribute_offset': field['attribute_offset'], 'editable': field['editable'],
                'intensity': 'bright' if 'BRT' in field['attributes'] else 'normal', 'cursor': 'IC' in field['attributes']}
        value = "values[" + repr(field['id']) + "]" if field['editable'] else repr(field['initial'])
        lines += ['    # BMS field ' + field['id'] + '; ' + field['source_path'] + ':' + str(field['start_line']) + '-' + str(field['end_line']),
                  '    fields.append(' + repr(item)[:-1] + ", 'value': " + value + '})']
    cursor = next((field['id'] for field in reversed(screen['fields']) if 'IC' in field['attributes']), None)
    header = {'mapset': screen['mapset'], 'map': screen['map'], 'rows': screen['rows'], 'columns': screen['columns'], 'cursor_field': cursor}
    lines.append("    return {'input_status': 'ACCEPT_INPUT', 'screen': " + repr(header)[:-1] + ", 'fields': fields}, 'return_code': 0}")
    return '\n'.join(lines) + '\n'


def prepare_screen(code):
    """Restrict capabilities of the fixed screen generator and its mutations."""
    require(isinstance(code, str) and len(code.encode()) <= 2 * 1024 * 1024, 'Screen target exceeds the code bound')
    tree = ast.parse(code); require(len(tree.body) == 1 and isinstance(tree.body[0], ast.FunctionDef) and tree.body[0].name == 'run_screen', 'Only one generated screen function is accepted')
    function = tree.body[0]
    require(function.returns is None and function.args.args and function.args.args[0].annotation is None, 'Screen target annotations are forbidden')
    require(len(function.args.args) == 1 and function.args.args[0].arg == 'values' and not function.args.defaults and not function.args.kwonlyargs and not function.args.posonlyargs and function.args.vararg is None and function.args.kwarg is None and not function.decorator_list, 'Screen target accepts exactly one values argument')
    allowed = (ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Assign, ast.Name, ast.Load, ast.Store, ast.Call, ast.Dict, ast.Constant, ast.List, ast.If, ast.Compare, ast.BoolOp, ast.And, ast.Or, ast.Eq, ast.NotEq, ast.Lt, ast.Gt, ast.IsNot, ast.NotIn, ast.Subscript, ast.Expr, ast.Attribute, ast.Return, ast.GeneratorExp, ast.comprehension)
    for node in ast.walk(tree):
        require(isinstance(node, allowed), 'Screen target includes an unsupported executable capability')
        if isinstance(node, ast.FunctionDef): require(node is function, 'Nested screen functions are forbidden')
        if isinstance(node, ast.Name): require(node.id in {'run_screen', 'values', 'errors', 'fields', 'type', 'dict', 'str', 'len', 'any', 'ord', 'c'}, 'Unknown screen target identifier')
        if isinstance(node, ast.Attribute): require(isinstance(node.value, ast.Name) and ((node.value.id in {'errors', 'fields'} and node.attr == 'append') or (node.value.id == 'values' and node.attr == 'get')), 'Unsafe screen target attribute')
        if isinstance(node, ast.Call): require(len(node.args) == 1 and not node.keywords and ((isinstance(node.func, ast.Name) and node.func.id in {'type', 'len', 'any', 'ord'}) or (isinstance(node.func, ast.Attribute) and node.func.attr in {'append', 'get'})), 'Unsafe screen target call')
        if isinstance(node, ast.Assign): require(len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in {'errors', 'fields'} and isinstance(node.value, ast.List) and not node.value.elts, 'Unsafe screen target assignment')
        if isinstance(node, ast.comprehension): require(isinstance(node.target, ast.Name) and node.target.id == 'c' and not node.ifs and not node.is_async and isinstance(node.iter, ast.Call) and isinstance(node.iter.func, ast.Attribute) and node.iter.func.attr == 'get', 'Unsafe screen validation comprehension')
    namespace = {'__builtins__': {}, 'type': type, 'dict': dict, 'str': str, 'len': len, 'any': any, 'ord': ord}
    exec(compile(tree, '<source-generated-screen>', 'exec'), namespace)
    return namespace['run_screen']


def screen_target_mappings(code, screen):
    require(code == emit_screen(screen), 'Screen target differs from its source-owned generated contract')
    body = ast.parse(code).body[0].body; result = {}
    field_nodes = [node for node in body if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute) and isinstance(node.value.func.value, ast.Name) and node.value.func.value.id == 'fields']
    for field, node in zip(screen['fields'], field_nodes):
        result[field['id']] = {'start': node.lineno, 'end': node.end_lineno}
    result['layout'] = {'start': ast.parse(code).body[0].lineno, 'end': body[-1].end_lineno}
    return result


def plan_screen_cases(screen, seed, minimum=20, budget=4096, checkpoint=None, fixture_contract_version=4):
    """Freeze source expectations before actual target comparison.

    Distinctness per input field uses that field's executed value. The layout
    technical unit uses complete source-valid records, just like fixture v4.
    Static-only screens have a one-state domain and remain explicitly limited.
    """
    if checkpoint: checkpoint()
    validate_screen(screen)
    require(type(fixture_contract_version) is int and fixture_contract_version in (4,5), 'Unsupported screen fixture contract version')
    if fixture_contract_version == 5:
        require(type(minimum) is int and minimum == 64, 'V5 screen fixtures require a base floor of 64')
        require(type(budget) is int and minimum <= budget <= 4096, 'V5 screen case budget must be 64..4096')
    require(type(seed) is int and 0 <= seed < 2 ** 63, 'Screen seed must be an unsigned 63-bit integer')
    require(type(minimum) is int and minimum >= 20 and type(budget) is int and minimum <= budget <= 10000, 'Screen fixtures require at least 20 distinct valid states within the case budget')
    inputs = [field for field in screen['fields'] if field['editable']]
    rng = random.Random(seed); records = []; seen = set(); required_boundaries = set(); alphabet = ''.join(chr(i) for i in range(32, 127))
    def add(values, randomized, label):
        if checkpoint: checkpoint()
        key = sha(encode(values))
        if fixture_contract_version == 5 and label in ('source_defaults', 'character_boundary', 'source_field_boundary'):
            required_boundaries.add(key)
        if key in seen: return
        if fixture_contract_version == 5 and len(records) >= budget: return
        seen.add(key); records.append({'id': 'SCREEN_CASE_' + str(len(records) + 1).zfill(4), 'values': values,
                                      'randomized': randomized, 'kind': label, 'expected': screen_reference(screen, values)})
    defaults = {field['id']: field['initial'] for field in inputs}
    add(defaults, False, 'source_defaults')
    for boundary in (' ', '0', '9', 'A', '~'):
        add({field['id']: boundary * field['width'] for field in inputs}, False, 'character_boundary')
    if fixture_contract_version == 5:
        for field in inputs:
            for value in (' ' * field['width'], '0' * field['width'], '9' * field['width'],
                          'A'.ljust(field['width']), 'A'.rjust(field['width']), '~' * field['width']):
                add({**defaults, field['id']: value}, False, 'source_field_boundary')
    for _ in range(minimum * 8 if inputs else 0):
        if len(records) >= budget: break
        add({field['id']: ''.join(rng.choice(alphabet) for _ in range(field['width'])) for field in inputs}, True, 'runtime_randomized')
        if sum(record['randomized'] for record in records) >= minimum and all(len({record['values'][field['id']] for record in records if record['randomized']}) >= minimum for field in inputs): break
    valid = list(records)
    negatives = [None, [], {'unexpected': 'x'}]
    for field in inputs:
        for value in (None, 1, True, '', 'A' * (field['width'] + 1), '\n' * field['width'], 'é' * field['width']):
            values = dict(defaults); values[field['id']] = value; negatives.append(values)
    if fixture_contract_version == 5:
        for field in inputs:
            negatives.append({name: value for name, value in defaults.items() if name != field['id']})
            for value in (0.0, [], {}):
                negatives.append({**defaults, field['id']: value})
        for field in screen['fields']:
            if not field['editable']: negatives.append({**defaults, field['id']: field['initial']})
        negatives = list({sha(encode(values)): values for values in negatives}.values())
    for values in negatives:
        if checkpoint: checkpoint()
        if len(records) >= budget: break
        records.append({'id': 'SCREEN_CASE_' + str(len(records) + 1).zfill(4), 'values': values,
                        'randomized': False, 'kind': 'invalid_target_request', 'expected': screen_reference(screen, values)})
    counts = {field['id']: len({record['values'][field['id']] for record in valid if record['randomized']}) for field in inputs}
    layout_count = len({sha(encode(record['values'])) for record in valid if record['randomized']})
    constant_fields = {field['id']: {'distinct_source_display_values': 1,
                       'randomized_input_context_witnesses': layout_count,
                       'source_value_hash': sha(field['initial']),
                       'basis': f'One constant INITIAL display value compared across distinct valid input contexts; this is not {minimum} distinct display values.' if fixture_contract_version==5 else 'One constant INITIAL display value compared across distinct valid input contexts; this is not twenty distinct display values.'}
                       for field in screen['fields'] if not field['editable']}
    gaps = [{'kind': 'screen_state_deficit', 'field': name, 'required': minimum, 'observed': count,
             'reason': 'Distinct randomized source-valid states are below the required minimum; duplicates and unrelated-field padding do not count.'}
            for name, count in counts.items() if count < minimum]
    if fixture_contract_version == 5 and required_boundaries - seen:
        gaps.append({'kind': 'screen_boundary_budget_deficit', 'required': len(required_boundaries),
                     'observed': len(required_boundaries & seen), 'record_hashes': sorted(required_boundaries - seen),
                     'reason': 'The budget omitted mandatory source-valid field boundary states; no layout verification credit.'})
    if len(records)-len(valid)<len(negatives):
        gaps.append({'kind':'screen_negative_budget_deficit','required':len(negatives),'observed':len(records)-len(valid),
                     'reason':'The case budget omitted mandatory malformed target requests; each supported field input guard needs its own negative witnesses.'})
    if layout_count < minimum:
        gaps.append({'kind': 'screen_layout_state_deficit', 'required': minimum, 'observed': layout_count,
                     'reason': (f'Static-only layouts have one valid input state; they do not receive fabricated {minimum}-state validation credit.' if fixture_contract_version==5 else 'Static-only layouts have one valid input state; they do not receive fabricated twenty-state validation credit.') if not inputs else 'Randomized complete layout records are below the required minimum.'})
    result = {'schema_version': 1, 'profile': PROFILE, 'screen_id': screen['id'], 'source_hash': screen['source_hash'],
            'target_hash': sha(emit_screen(screen)), 'contract_hash': sha(encode(screen)), 'seed': seed,
            'minimum': minimum, 'budget': budget, 'cases': records,
            'coverage': {'complete': not gaps, 'fields': counts, 'constant_fields': constant_fields,
                         'layout_randomized_states': layout_count,
                         'gaps': gaps, 'invalid_cases': len(records) - len(valid),
                         'distinctness_basis': 'SOURCE_FIELD_VALUE_AT_EXECUTION_AND_COMPLETE_LAYOUT_RECORDS',
                         'linked_map_witness': {'mapset': screen['mapset'], 'map': screen['map'], 'source_path': screen['source_path'], 'source_hash': screen['source_hash']}},
            'evidence_basis': 'SOURCE_DERIVED_EXPECTED', 'observed_mainframe_parity': False}
    if fixture_contract_version == 5:
        result['fixture_contract_version'] = 5
        result['coverage']['qualification'] = '64_SOURCE_VALID_FIELD_AND_LAYOUT_STATES_PLUS_SOURCE_BOUNDARIES_AND_DISTINCT_INVALID_REQUESTS'
    return result


def verify_screen(screen, code, suite, checkpoint=None):
    require(encode(suite) == encode(plan_screen_cases(screen, suite['seed'], suite['minimum'], suite['budget'], checkpoint=checkpoint, fixture_contract_version=suite.get('fixture_contract_version',4))), 'Frozen screen source expectations differ from their contract')
    require(code == emit_screen(screen) and sha(code) == suite['target_hash'], 'Screen target differs from its frozen generated version')
    run = prepare_screen(code); actual = []; differences = []
    for case in suite['cases']:
        if checkpoint: checkpoint()
        result = run(case['values']); actual.append({'id': case['id'], 'actual': result})
        if encode(result) != encode(case['expected']): differences.append(case['id'])
    return {'passed': not differences and suite['coverage']['complete'], 'cases': len(actual),
            'differences': differences, 'actual': actual, 'coverage': suite['coverage'],
            'target_hash': sha(code), 'source_hash': screen['source_hash'],
            'evidence_basis': 'SOURCE_DERIVED_EXPECTED', 'native_controller_verified': False,
            'observed_mainframe_parity': False}


def adversarial_screen(screen, code, suite, checkpoint=None):
    """Execute focused mutants until their first actual divergence witness.

    Field-output mutations need one complete valid layout context. Input guards
    need the exact malformed request they protect. Cases are not all replayed for
    each mutant; the independent complete target comparison remains mandatory.
    Candidate code is streamed to keep memory bounded by one target version.
    """
    if checkpoint: checkpoint()
    require(code == emit_screen(screen), 'Screen adversarial review requires its frozen target')
    require(encode(suite) == encode(plan_screen_cases(screen, suite['seed'], suite['minimum'], suite['budget'], checkpoint=checkpoint, fixture_contract_version=suite.get('fixture_contract_version',4))), 'Screen adversarial expectations differ from source')
    lines = code.splitlines(); field_lines = {}
    for line in lines:
        if 'fields.append(' in line:
            ident = re.search(r"'id': '([^']+)'", line)
            require(ident is not None, 'Screen mutation field has no source-owned identity')
            field_lines[ident[1]] = line
    valid = next((case for case in suite['cases'] if case['expected'].get('input_status') == 'ACCEPT_INPUT'), None)
    negatives = [case for case in suite['cases'] if case['kind'] == 'invalid_target_request']
    shape = next((case for case in negatives if isinstance(case['values'], dict) and 'field set differs from selected BMS input layout' in case['expected'].get('errors', [])), None)
    field_negatives = {}
    for field in screen['fields']:
        if field['editable']:
            message = field['id'] + ': invalid fixed-width printable ASCII characters'
            field_negatives[field['id']] = next((case for case in negatives if case['expected'].get('errors') == [message]), None)
    def candidates():
        for field in screen['fields']:
            original = field_lines[field['id']]
            for key, value in [('row', (field['attribute_offset'] + 1) // screen['columns'] + 1),
                               ('column', (field['attribute_offset'] + 1) % screen['columns'] + 1),
                               ('width', field['width']), ('editable', field['editable'])]:
                replacement = not value if type(value) is bool else value + 1
                mutated = original.replace(repr(key) + ': ' + repr(value), repr(key) + ': ' + repr(replacement), 1)
                yield field['id'] + ':' + key, code.replace(original, mutated, 1), [valid] if valid else []
            if not field['editable'] and field['width']:
                replacement = ('!' if field['initial'][0] != '!' else '?') + field['initial'][1:]
                mutated = original.replace("'value': " + repr(field['initial']), "'value': " + repr(replacement), 1)
                yield field['id'] + ':default', code.replace(original, mutated, 1), [valid] if valid else []
        for number, line in enumerate(lines):
            witness = None
            if line.startswith('    if type(values) is not dict:'):
                witness = next((case for case in negatives if case['values'] is None), None)
            elif line.startswith('    if len(values)'):
                witness = shape
            elif line.startswith('    if ') and 'type(values.get(' in line:
                for field in screen['fields']:
                    if field['editable'] and 'values.get(' + repr(field['id']) + ')' in line:
                        witness = field_negatives.get(field['id']); break
            else: continue
            yield 'input_guard:' + str(number + 1), code.replace(line, '    if False:', 1), [witness] if witness else []
    results = []
    for name, candidate, cases in candidates():
        if checkpoint: checkpoint()
        detected = []; checked = []; capability_denied = False
        try: run = prepare_screen(candidate)
        except (ValidationError, SyntaxError, ValueError):
            run = None; capability_denied = True
        if run:
            for case in cases:
                if checkpoint: checkpoint()
                checked.append(case['id'])
                try: actual = run(case['values']); differs = encode(actual) != encode(case['expected'])
                except Exception: differs = True
                if differs:
                    detected.append(case['id']); break
        results.append({'id': name, 'detected': bool(detected) or capability_denied,
                        'witness_cases': detected, 'witness_count': len(detected),
                        'checked_cases': checked, 'checked_case_count': len(checked),
                        'capability_denied': capability_denied, 'mutant_hash': sha(candidate)})
    return {'passed': bool(results) and all(result['detected'] for result in results), 'mutations': results,
            'source_hash': screen['source_hash'], 'target_hash': sha(code),
            'scope': 'Field layout/default/protection and malformed request guards; each mutant stops at its first actual divergence witness. Native controller semantics remain unverified.'}
