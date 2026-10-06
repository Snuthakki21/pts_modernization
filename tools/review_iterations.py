"""Run thirty distinct review passes and preserve machine-readable evidence.

Run from the repository with its locked Python environment. This reviews the
workbench implementation using fictional/local fixtures; it never accesses a
live mainframe or supplies answers for an operational SME packet.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
PASSES=[
 ('Setup installation failures','test_review_integrity.SetupScriptTests'),
 ('Manifest row loss and identity collisions','test_intake_hardening'),
 ('Forged Excel dimensions and hidden scope','test_iteration_regressions'),
 ('Portable paths and enforced folder ownership','test_layout','test_foundation'),
 ('Offline preflight and resource bounds','test_preflight'),
 ('Complete export and selected inventory','test_adversarial.AdversarialTests.test_all_export_paths_survive_asset_selection','test_coverage.CoverageTests.test_inventory_preserves_every_original_line_and_explicit_scope'),
 ('Structural mainframe file classification','test_source_classification'),
 ('Knowledge provenance and immutable snapshots','test_knowledge_workflow'),
 ('COPY closure and ambiguity','test_source.SourceTests.test_copybook_source_hash_and_rule_evidence','test_adversarial.AdversarialTests.test_ambiguous_copy_candidates_stay_in_selected_accounting','test_source_classification.ClassifiedSourceTests.test_duplicate_extensionless_copybooks_do_not_choose_first_match'),
 ('JCL grammar and ordered source reconciliation','test_source.SourceTests.test_unsupported_jcl_options_and_manifest_disagreement_block','test_adversarial.AdversarialTests.test_dd_requires_io_adapter','test_adversarial.AdversarialTests.test_duplicate_jcl_job_declarations_are_not_merged'),
 ('Standard and custom utility contracts','test_mainframe'),
 ('COBOL storage and division lifetime','test_adversarial.AdversarialTests.test_working_storage_is_not_treated_as_caller_record','test_adversarial.AdversarialTests.test_missing_divisions_and_duplicate_groups_block'),
 ('Statement boundaries and unsupported syntax','test_adversarial.AdversarialTests.test_sentence_period_cannot_end_if_scope_silently','test_adversarial.AdversarialTests.test_malformed_move_literal_is_not_swallowed','test_source.SourceTests.test_unknown_statement_blocks_without_losing_source_lines','test_source.SourceTests.test_missing_copybook_and_nested_if_are_accounted'),
 ('Numeric limits and fixed-width string semantics','test_source.SourceTests.test_string_field_ordering_and_out_of_range_initializers_block','test_source.SourceTests.test_cobol_string_comparisons_pad_literal_and_free_indentation','test_adversarial.AdversarialTests.test_lowercase_numeric_picture','test_adversarial.AdversarialTests.test_comment_marker_inside_literal'),
 ('Decision precedence and sequential effects','test_adversarial.AdversarialTests.test_and_precedes_or_and_quoted_literals_stay_case_sensitive','test_source.SourceTests.test_source_threshold_else_and_sequential_effect'),
 ('Synthetic witnesses and case-budget gaps','test_adversarial.AdversarialTests.test_budget_exhaustion_explains_missing_boundary_obligations','test_source.SourceTests.test_boundary_witnesses_and_mutated_target_detected'),
 ('Independent expectations and forged oracles','test_adversarial.AdversarialTests.test_frozen_oracle_and_coverage_cannot_be_forged'),
 ('Exported target input and executable capabilities','test_target_boundary','test_source.SourceTests.test_target_cannot_import_or_call_unknown_functions'),
 ('Every-rule mutations and masked effects','test_adversarial.AdversarialTests.test_mutation_reports_masked_effect_without_false_credit','test_adversarial.AdversarialTests.test_adversarial_review_covers_each_rule_and_effect'),
 ('Job dispatch, record propagation and tampered templates','test_source.SourceTests.test_generated_jobs_propagate_record_to_next_step','test_adversarial.AdversarialTests.test_orchestration_rejects_modified_template_before_execution','test_coverage.CoverageTests.test_jcl_exec_maps_its_exact_job_step_when_program_is_reused'),
 ('SME workbook identity and complete context','test_review_integrity.ReviewIntegrityTests'),
 ('Single human return and deterministic agent continuation','test_workflow','test_runner'),
 ('Crash recovery, controls and retry limits','test_recovery'),
 ('Full source coverage and revoked conversion credit','test_coverage'),
 ('Target SQLite evidence and cancelled execution','test_coverage.CoverageTests.test_frozen_target_database_tampering_cannot_receive_credit','test_coverage.CoverageTests.test_cancelled_accountability_never_executes_targets'),
 ('MCP protocol, sessions and paginated discovery','test_connectors.MCPProtocolTests','test_connectors.DiscoveryTests'),
 ('Read-only gateway and SQL boundaries','test_connectors.GatewayTests','test_integrations.IntegrationTests.test_catalog_queries_are_read_only_and_bound_identifiers','test_integrations.IntegrationTests.test_zowe_rejects_injected_dataset_and_write_command'),
 ('LLM consent, usage and suggestion authority','test_integrations.IntegrationTests.test_provider_requires_egress_permission_and_records_actual_usage','test_knowledge_workflow.KnowledgeWorkflowTests.test_optional_provider_receives_bounded_frozen_classification_context'),
 ('Metrics, scope, report acceptance and PPT','test_portfolio_scope','test_reports'),
 ('Production HTTP workflow and visible UI contracts','test_http','test_api','test_knowledge_api'),
]


def fingerprint():
    digest=hashlib.sha256()
    for folder in ('workbench','tests','tools','scripts','knowledge','frontend/src'):
        for path in sorted((ROOT/folder).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                digest.update(path.relative_to(ROOT).as_posix().encode()+b'\0'+hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def run(output):
    from workbench.domain import safe_path, require
    output=Path(output).absolute()
    require(output.is_relative_to(ROOT/'.implementation'), 'Review evidence belongs under .implementation; publish only the reviewed consolidated report')
    safe_path(ROOT,output.relative_to(ROOT).as_posix())
    require(not output.exists(),'Use a new review evidence directory; never overwrite a previous pass')
    output.mkdir(parents=True)
    # Audit fixtures must not inherit credentials or source connections.
    env={key:value for key,value in os.environ.items() if not key.startswith('WB_')}
    env['PYTHONPATH']=os.pathsep.join((str(ROOT),str(ROOT/'tests')))
    # Some restricted hosts otherwise put unittest TemporaryDirectory at root.
    temp=ROOT/'.implementation/tmp';temp.mkdir(parents=True,exist_ok=True);env['TMPDIR']=str(temp)
    before=fingerprint();rows=[]
    for number,(focus,*tests) in enumerate(PASSES,1):
        command=[sys.executable,'-m','unittest','-v',*tests]
        started=time.monotonic()
        try:
            result=subprocess.run(command,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180)
            log=result.stdout;code=result.returncode
        except subprocess.TimeoutExpired as exc:
            captured=exc.stdout or b'';log=(captured.decode(errors='replace') if isinstance(captured,bytes) else captured)+'\nReview pass exceeded its 180-second bound.\n';code=124
        (output/f'pass-{number:02d}.log').write_text(log,encoding='utf-8')
        count=re.search(r'^Ran (\d+) tests? in ',log,re.M)
        row={'iteration':number,'focus':focus,'tests':tests,'tests_run':int(count[1]) if count else 0,
             'status':'PASS' if code==0 and count and int(count[1])>0 else 'FAIL',
             'exit_code':code,'seconds':round(time.monotonic()-started,3),'log_sha256':hashlib.sha256(log.encode()).hexdigest()}
        rows.append(row);print(f'{number:02d}/30 {row["status"]}: {focus} ({row["tests_run"]} tests)',flush=True)
    after=fingerprint()
    report={'schema_version':1,'created':datetime.now(timezone.utc).isoformat(),
            'method':'Thirty distinct focused regression/adversarial passes; some gates deliberately overlap. This is not thirty complete-suite runs or an exhaustive proof.',
            'source_fingerprint':before,'source_unchanged_during_review':before==after,
            'iterations':rows,'iterations_completed':len(rows),'passed':sum(x['status']=='PASS' for x in rows),
            'failed':sum(x['status']=='FAIL' for x in rows),'test_executions':sum(x['tests_run'] for x in rows),
            'limitations':['Local fictional fixtures; live source/provider connections not exercised','Unsupported native semantics remain blocked','Finite tests cannot prove zero defects or universal equivalence']}
    (output/'review.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('iterations_completed','passed','failed','test_executions','source_unchanged_during_review')}),flush=True)
    return 0 if len(rows)==30 and report['failed']==0 and before==after else 2


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default=str(ROOT/'.implementation/tmp'/('review-'+uuid.uuid4().hex)))
    args=parser.parse_args();raise SystemExit(run(args.output))
