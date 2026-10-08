"""Versioned target boundary; only implemented, verified backends are selectable."""
from dataclasses import dataclass
from typing import Protocol
from copy import deepcopy
from .domain import require


class TargetBackend(Protocol):
    """Language/database-independent boundary over the frozen source model.

    A future implementation must pass generation, replay, type/error,
    linked-state and adversarial gates before joining get_backend's allowlist.
    Discovery, ledger, requirements and review do not depend on its language.
    """
    name: str
    contract_version: int
    def capabilities(self) -> dict: ...
    def generate(self, program: dict) -> str: ...
    def compare(self, program: dict, code: str, suite: dict, **options) -> dict: ...


LEGACY_FIDELITY_REQUIREMENT = (
    'Preserve evidenced legacy behavior one-for-one, including known legacy design defects. '
    'Never silently repair source business or technical logic. A legacy defect alone is not an exclusion or unsupported-logic reason. '
    'Refactor only with equivalent observable behavior '
    'and source/target/test evidence. Keep functionality-specific Db2 utilities/programs without verified '
    'equivalents as named unverified gaps; labels, age, a plan or SME Yes cannot prove a replacement. '
    'Explicit saved No remains an accounted omission, not parity.'
)


TARGET_EXTENSION_CONTRACT = {
    'version': 1,
    'implemented': ['python-sqlite'],
    'future_candidates': ['python-oracle', 'python-bigquery', 'java', 'dotnet'],
    'fixed_source_access': ['read_only_zowe_cli', 'approved_read_only_db2_mcp'],
    'required': [LEGACY_FIDELITY_REQUIREMENT, 'versioned source model and target artifacts', 'selected requirement mappings',
                 'generation and actual execution comparisons', 'types, failures and transactional semantics',
                 '20 distinct randomized valid logic states with linked witnesses',
                 'independent adversarial review and immutable report gates'],
    'bigquery_boundary': 'A warehouse target requires source-equivalent workload and transaction qualification; it is not an automatic transactional Db2 replacement. Behavior-changing redesign cannot earn migration parity credit.',
}


@dataclass(frozen=True)
class PythonSQLiteBackend:
    name: str = 'python-sqlite'
    contract_version: int = 1

    def capabilities(self):
        return {'name': self.name, 'contract_version': self.contract_version,
                'source_profile': 'Existing flat IF / literal MOVE record adapter',
                'database': 'SQLite comparison storage; native Db2 parity is not implied',
                'evidence_basis': 'SOURCE_DERIVED_EXPECTED',
                'behavior_fidelity': LEGACY_FIDELITY_REQUIREMENT}

    def generate(self, program):
        from .target import emit_program
        return emit_program(program)

    def compare(self, program, code, suite, **options):
        from .fixtures import verify_program
        return verify_program(program, code, suite, **options)


def get_backend(name='python-sqlite'):
    require(name == 'python-sqlite', 'Target backend is not implemented and verified: '+str(name))
    return PythonSQLiteBackend()


def adapter_fingerprint():
    """Detect on-disk adapter edits before an existing service refreshes analysis."""
    from pathlib import Path
    from .domain import encode, sha
    root=Path(__file__).parent
    files=sorted(root.glob('*.py'))+[root/'static'/'online.js']
    return sha(encode({p.relative_to(root).as_posix():sha(p.read_bytes()) for p in files if p.is_file()}))


# Versioned advice only. These facts cannot register a backend, alter a frozen
# target choice, or satisfy the Coordinator's generation/comparison gates.
ARCHITECTURE_REFERENCES = (
    ('oracle_nulls', 'Oracle Database 21c: null and zero-length character values',
     'https://docs.oracle.com/en/database/oracle/oracle-database/21/sqlrf/Nulls.html'),
    ('oracle_transactions', 'python-oracledb: transaction management',
     'https://python-oracledb.readthedocs.io/en/latest/user_guide/txn_management.html'),
    ('sqlite_types', 'SQLite: type affinity and storage classes',
     'https://www.sqlite.org/datatype3.html'),
    ('sqlite_foreign_keys', 'SQLite: foreign-key enforcement',
     'https://www.sqlite.org/foreignkeys.html'),
    ('sqlite_transactions', 'SQLite: transaction and concurrency behavior',
     'https://www.sqlite.org/lang_transaction.html'),
)

# General qualification work, not a finding that every source uses each feature.
ARCHITECTURE_OBLIGATIONS = (
    ('schema_and_sql', 'Map the complete database contract', (
        'Source DDL, keys, constraints, indexes, triggers, routines, packages and privileges with object provenance',
        'Static and dynamic SQL, bind variables, cursors, SQLCODE/SQLSTATE branches and row-count behavior; map each to target statements and tests',
        'Release-specific SQL and driver behavior; naming and configuration alone do not establish compatibility',
    ), ()),
    ('types_and_nulls', 'Preserve data and comparison semantics', (
        'Exact decimal precision/scale, rounding, overflow, binary/packed formats, CCSID and character padding/collation',
        'Distinguish NULL, empty text and blank-padded values; Oracle 21c treats zero-length character values as NULL, so verify any required distinction in the chosen release',
        'Dates, timestamps, time zones, large objects and host-variable indicators; explicitly enforce target types and constraints',
    ), ('oracle_nulls', 'sqlite_types', 'sqlite_foreign_keys')),
    ('transactions_and_recovery', 'Prove transaction and recovery boundaries', (
        'Commit/rollback scope across programs, cursors and external effects; Oracle DDL commits and driver autocommit behavior require explicit migration boundaries',
        'Isolation, concurrent writers, locks, deadlocks, retries, idempotency, partial failures and restart/checkpoint behavior',
        'Target foreign-key enforcement and commit/rollback tests on the actual selected database; SQLite comparisons alone cannot qualify Oracle',
    ), ('oracle_transactions', 'sqlite_transactions', 'sqlite_foreign_keys')),
    ('target_adapter', 'Implement and qualify the target adapter', (
        'Versioned generation, binding and comparison adapter through the existing Coordinator, immutable evidence and report gates',
        'At least 20 distinct valid runtime-generated states per supported logic item, recorded seeds, replayable unit tests, linked-data witnesses, actual target comparisons and adversarial checks',
        'Native source-only behaviors remain named unverified obligations until an equivalent replacement and evidence exist',
    ), ()),
    ('operations', 'Qualify deployment and operations', (
        'Windows and Linux driver/package compatibility, approved secrets/TLS, authentication, authorization and least privilege',
        'Measured data volume, concurrency, latency, connection/pool limits, availability and backup/restore requirements',
        'Reconciliation, migration/cutover rollback, audit and monitoring evidence plus infrastructure and licensing decisions',
    ), ()),
)


def _database_evidence(doc):
    """Reuse source classification/lineage, never infer SQL from member names."""
    from .domain import sha
    analysis = doc.get('analysis') or {}
    assets = {asset['path']: asset for asset in analysis.get('assets', []) if asset.get('selected', True)}
    evidence = []; seen = set(); validated = {}

    def add(path, first, last, kind, reason, **extra):
        asset = assets.get(path)
        if asset is None or type(first) is not int or type(last) is not int:
            return
        # Validate only referenced candidates and count their lines once. A view
        # refresh must not rehash every unrelated member in a large export.
        if path not in validated:
            text = asset.get('source_text')
            validated[path] = (len(text.splitlines()) if isinstance(text, str)
                               and asset.get('source_hash') == sha(text) else 0)
        if not 1 <= first <= last <= validated[path]:
            return
        row = {'kind': kind, 'path': path, 'start_line': first, 'end_line': last,
               'source_hash': asset['source_hash'], 'reason': reason, **extra}
        identity = (path, first, last, kind, extra.get('object'))
        if identity not in seen:
            seen.add(identity); evidence.append(row)

    for path, classification in sorted(analysis.get('classifications', {}).items()):
        if (classification.get('kind') not in ('sql', 'dclgen')
                or classification.get('confidence') != 'structural' or classification.get('conflicts')):
            continue
        for ref in classification.get('evidence', []):
            add(path, ref.get('line'), ref.get('line'), 'database_source',
                'Structural ' + classification['kind'] + ' evidence; target semantics remain unverified')
    for node in (doc.get('lineage') or {}).get('nodes', []):
        if node.get('kind') != 'db2_table' or not node.get('selected'):
            continue
        for ref in node.get('evidence', []):
            add(ref.get('path'), ref.get('line'), ref.get('end_line', ref.get('line')),
                'database_dependency', 'Selected static or unresolved database dependency; not proof of installed objects or executable support',
                object=node.get('name', 'Unknown'))
    return sorted(evidence, key=lambda row: (row['path'], row['start_line'], row['end_line'], row['kind'], row.get('object', '')))


def target_architecture(doc):
    """Project a provisional architectural decision without changing execution.

    Oracle remains a candidate only. A source-evidenced need for database design
    is not enough to choose Oracle: deployment, transaction and performance
    requirements and an implemented adapter are still missing. Historical
    documents with only suffix-based classification are not promoted to facts.
    """
    evidence = _database_evidence(doc)
    analysis = doc.get('analysis') or {}
    backend = doc.get('target_backend') or {'name': 'python-sqlite', 'contract_version': 1}
    active_name = backend.get('name', 'python-sqlite')
    active_version = backend.get('contract_version', 1)
    implemented = active_name == 'python-sqlite' and type(active_version) is int and active_version == 1
    recommendation = 'assess_database_target' if evidence else 'retain_bounded_python_sqlite'
    status = 'ASSESSMENT_REQUIRED' if evidence else 'BASELINE_RETAINED' if analysis else 'ASSESSMENT_INCOMPLETE'
    title = 'Assess the application database target' if evidence else 'Retain the bounded Python/SQLite baseline'
    rationale = (
        'Selected source contains database definitions or dependencies. Compare Python/Oracle and Python/SQLite against source semantics, workload and operational requirements before selecting the application database.'
        if evidence else
        'Available evidence does not establish a database migration design. Keep the implemented record adapter and comparison storage within their tested scope; absence of a detected database reference does not prove the application has no database behavior.'
    )
    if not implemented:
        status = 'UNIMPLEMENTED_TARGET'; recommendation = 'resolve_unimplemented_target'
        title = 'Resolve the unimplemented target contract'
        rationale = 'The recorded target contract is not implemented. Architectural advice cannot authorize generation or convert this contract into a supported backend.'
    return {
        'schema_version': 1, 'policy_version': 1, 'process_id': doc.get('id'),
        'source_snapshot': analysis.get('source_snapshot'), 'status': status,
        'recommendation': recommendation, 'title': title, 'rationale': rationale,
        'active_backend': {'name': active_name, 'contract_version': active_version, 'implemented': implemented,
                           'scope': 'Bounded Python record adapter and SQLite comparison storage; no migrated application database is implied'},
        'production_ready': False,
        'extension_contract': deepcopy(TARGET_EXTENSION_CONTRACT),
        'candidates': [
            {'name': 'python-sqlite', 'title': 'Python / SQLite', 'selectable': True,
             'implementation_status': 'BOUNDED_ADAPTER_IMPLEMENTED', 'native_db2_parity_verified': False,
             'scope': 'Supported flat COBOL record logic; SQLite stores comparison results and local session state',
             'rationale': 'Retain for the current bounded POC. Application SQL, types, constraints and concurrency require separate source-supported adapters and database qualification.'},
            {'name': 'python-oracle', 'title': 'Python / Oracle', 'selectable': False,
             'implementation_status': 'NOT_IMPLEMENTED', 'native_db2_parity_verified': False,
             'scope': 'Future database target candidate; no Oracle generation, execution or connection is implemented',
             'rationale': 'Consider only after source, transactional, workload and operational requirements justify it and the target adapter passes the same evidence gates.'},
            *[{'name':name,'title':title,'selectable':False,'implementation_status':'NOT_IMPLEMENTED',
               'native_db2_parity_verified':False,'scope':'Future target adapter candidate; no generation or execution implemented',
               'rationale':rationale} for name,title,rationale in (
                   ('python-bigquery','Python / BigQuery','Qualify source-equivalent warehouse workload, data types and transactions; behavior-changing redesign is outside migration parity and no transactional Db2 substitute is assumed.'),
                   ('java','Java','Implement source-model generation and native target comparisons behind the same Coordinator gates.'),
                   ('dotnet','.NET','Implement source-model generation and native target comparisons behind the same Coordinator gates.'))],
        ],
        'evidence': evidence[:50], 'evidence_count': len(evidence), 'evidence_complete': len(evidence) <= 50,
        'obligations': [{'id': identity, 'title': title, 'status': 'UNVERIFIED',
                         'required_evidence': list(items), 'reference_ids': list(refs)}
                        for identity, title, items, refs in ARCHITECTURE_OBLIGATIONS],
        'references': [{'id': identity, 'title': title, 'url': url}
                       for identity, title, url in ARCHITECTURE_REFERENCES],
        'service_design': {'default': 'modular_application', 'extraction_requires': [
            'Independent business responsibility and data ownership',
            'Verified transaction, error, retry and idempotency boundaries',
            'Measured independent deployment or scaling need; an API alone does not justify another service',
        ]},
    }
