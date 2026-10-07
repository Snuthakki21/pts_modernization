"""Validate local, observed Db2 catalog receipts without deriving executable DDL.

The caller owns immutable bytes and SHA-256/provenance bindings. Recognition of
this receipt establishes observed catalog facts only, never SQL conversion or
native database equivalence. Missing semantics remain explicit obligations.
"""
from datetime import datetime
import re

from .domain import decode, require, sha

_FIELDS = {'schema_version', 'kind', 'schema', 'table', 'columns',
           'description_complete', 'ddl', 'constraints', 'indexes', 'triggers', 'provenance'}
_COLUMN = {'NAME', 'COLNO', 'COLTYPE', 'LENGTH', 'SCALE', 'NULLS', 'CCSID', 'DEFAULT', 'DEFAULTVALUE'}
_PROVENANCE = {'origin', 'tool', 'locator', 'retrieved_at', 'environment', 'profile', 'encoding'}
_NAME = re.compile(r'[A-Z@$#][A-Z0-9@$#_]{0,127}')
MAX_CATALOG_BYTES = 512 * 1024


def table_description(text, provenance=None):
    """Return a validated typed receipt, None for ordinary source, reject malformed receipts.

    Receipt provenance must match the surrounding accepted retrieval provenance
    when provided. The full source hash is retained; JSON is never executed.
    """
    if not isinstance(text, str) or not text.lstrip().startswith('{'):
        return None
    # Only the explicit type claims this contract; arbitrary JSON stays unknown.
    if 'DB2_TABLE_DESCRIPTION' not in text:
        return None
    raw = text.encode('utf-8')
    require(len(raw) <= MAX_CATALOG_BYTES, 'Db2 catalog receipt exceeds 512 KiB')
    value = decode(raw, limit=MAX_CATALOG_BYTES)
    require(isinstance(value, dict) and set(value) == _FIELDS,
            'Db2 catalog receipt requires the exact typed table-description fields')
    require(type(value['schema_version']) is int and value['schema_version'] == 1
            and value['kind'] == 'DB2_TABLE_DESCRIPTION', 'Unsupported Db2 catalog receipt contract')
    for label in ('schema', 'table'):
        require(isinstance(value[label], str) and bool(_NAME.fullmatch(value[label])),
                'Db2 catalog receipt needs an exact uppercase unquoted ' + label)
    require(type(value['description_complete']) is bool, 'Db2 catalog completeness must be explicit')
    columns = value['columns']; names = set(); ordinals = set()
    require(isinstance(columns, list) and 0 < len(columns) <= 32768, 'Db2 catalog columns are required and bounded')
    for column in columns:
        require(isinstance(column, dict) and {'NAME', 'COLNO', 'COLTYPE', 'LENGTH', 'NULLS'} <= set(column)
                and set(column) <= _COLUMN, 'Db2 catalog column fields are incomplete or unsupported')
        require(isinstance(column['NAME'], str) and bool(_NAME.fullmatch(column['NAME']))
                and column['NAME'] not in names, 'Db2 catalog column identity is invalid or repeated')
        require(type(column['COLNO']) is int and 0 <= column['COLNO'] <= 32767
                and column['COLNO'] not in ordinals, 'Db2 catalog column ordinal is invalid or repeated')
        names.add(column['NAME']); ordinals.add(column['COLNO'])
        require(isinstance(column['COLTYPE'], str) and bool(re.fullmatch(r'[A-Z][A-Z0-9 ]{0,31}', column['COLTYPE']))
                and type(column['LENGTH']) is int and 0 <= column['LENGTH'] <= 2147483647
                and column['NULLS'] in ('Y', 'N'), 'Db2 catalog type/length/null facts are invalid')
        for key in ('SCALE', 'CCSID'):
            if key in column:require(type(column[key]) is int and 0 <= column[key] <= 65535, 'Db2 catalog ' + key + ' is invalid')
        for key in ('DEFAULT', 'DEFAULTVALUE'):
            if key in column:require(column[key] is None or isinstance(column[key], str) and len(column[key]) <= 4096, 'Db2 catalog default is invalid')
    require([c['COLNO'] for c in columns] == sorted(ordinals), 'Db2 catalog columns must preserve ordinal order')
    if value['description_complete']:
        require(ordinals == set(range(len(columns))), 'Complete Db2 column description has missing ordinals')
    observation = value['provenance']
    require(isinstance(observation, dict) and {'origin', 'tool', 'locator', 'retrieved_at'} <= set(observation)
            and set(observation) <= _PROVENANCE, 'Db2 catalog provenance is required')
    require(observation['origin'] == 'configured_mcp' and observation['tool'] == 'db2_describe_table',
            'Db2 catalog must come from the approved typed db2_describe_table MCP tool')
    for content in observation.values():
        require(isinstance(content, str) and 0 < len(content) <= 2000
                and not any(ord(c) < 32 for c in content), 'Db2 catalog provenance must be bounded text')
    try:timestamp = datetime.fromisoformat(observation['retrieved_at'].replace('Z', '+00:00'))
    except ValueError:require(False, 'Db2 catalog observation needs a timezone-aware timestamp')
    require(timestamp.tzinfo is not None, 'Db2 catalog observation needs a timezone-aware timestamp')
    require(observation['locator'] == value['schema'] + '.' + value['table'],
            'Db2 catalog locator must equal its exact qualified schema.table identity')
    if provenance is not None:
        require(all(provenance.get(k) == v for k, v in observation.items()),
                'Db2 catalog provenance differs from the accepted retrieval receipt')
    require(value['ddl'] is None or isinstance(value['ddl'], str) and 0 < len(value['ddl']) <= 128000,
            'Db2 catalog DDL must be actual bounded text or unknown')
    for key in ('constraints', 'indexes', 'triggers'):
        require(value[key] is None or isinstance(value[key], list) and len(value[key]) <= 1000
                and all(isinstance(item, dict) and item for item in value[key]),
                'Db2 catalog ' + key + ' must be observed records or unknown')
    missing = (["COLUMN_DESCRIPTION"] if not value['description_complete'] else [])
    missing.extend(key.upper() for key in ('ddl', 'constraints', 'indexes', 'triggers') if value[key] is None)
    missing.append('NATIVE_SQL_TRANSACTION_TYPE_AND_AUTHORIZATION_EQUIVALENCE')
    return {**value, 'source_hash': sha(raw), 'missing_semantics': missing,
            'basis': 'OBSERVED_TYPED_MCP_CATALOG_FACTS_NOT_EXECUTABLE_SOURCE_OR_EQUIVALENCE'}
