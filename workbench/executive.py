"""Small frozen decision view over the inspected report metric model."""
import html
import json
import re
from html.parser import HTMLParser
from pathlib import PurePosixPath
from .domain import require

PRIMARY_REPORT = 'executive-report.html'
EVIDENCE_FILES=frozenset({'economics.html','factory.html','rules.html','coverage.html','metrics.json','management.pptx','inspection.json','../../analysis/source-analysis.json'})
DENOMINATOR = ('Verified applicable in-scope physical source lines / all applicable in-scope physical source lines. '
               'Blocked and unverified lines remain in the denominator; comments, declarations without runtime behavior and excluded files are separate.')


def executive_summary(doc, metrics, coverage=None):
    """Pure projection; never execute targets or refresh accepted historical evidence."""
    m = metrics
    require(m.get('process_id') == doc['id'], 'Executive metrics belong to a different process')
    def count(key):
        value = m.get(key)
        require(type(value) is int and value >= 0, 'Executive metric must be a nonnegative integer: '+key)
        return value
    total = count('source_accounted_lines'); scope = count('source_in_scope_lines')
    excluded = count('source_out_of_scope_lines'); applicable = count('source_applicable_lines')
    converted = count('source_verified_applicable_lines'); blocked = count('source_blocked_lines')
    unverified = count('source_unverified_mapped_lines'); nonexecutable = count('source_non_executable_lines')
    require(scope+excluded == total and applicable+nonexecutable == scope
            and converted+blocked+unverified == applicable, 'Executive source denominators do not reconcile')
    integrity_errors=count('source_integrity_errors')
    eligible = (m.get('source_completion_eligible') is True and not doc.get('blockers')
                and m.get('source_full_accounting') is True and doc.get('packet_imported') is True
                and doc.get('verification_finished') is True
                and applicable > 0 and converted == applicable and not integrity_errors)
    status = 'CANCELLED' if doc.get('cancel_requested') or doc.get('status') == 'CANCELLED' else 'COMPLETED' if eligible else 'COMPLETED_WITH_BLOCKERS'
    actions = []
    if status == 'CANCELLED':
        actions.append('Preserve this cancelled run; authorize a new process before additional conversion.')
    else:
        if integrity_errors:
            actions.append('Recover the original missing or changed evidence; do not repin hashes or replace issued evidence.')
        if not doc.get('packet_imported'):
            actions.append('Return the one issued SME checklist with actual reviewer attribution; unanswered items remain unresolved.')
        if blocked:
            actions.append(f'Define and verify replacement behavior for {blocked:,} blocked source lines; retain the recorded scope.')
        if unverified:
            actions.append(f'Resolve the evidence or review gaps for {unverified:,} mapped but unverified source lines.')
        if doc.get('blockers') and len(actions) < 3:
            actions.append(f'Review {len(doc["blockers"]):,} recorded blockers in the linked evidence before accepting conversion.')
        if not actions:
            actions.append('Review the bounded POC result and agree the next validation scope before production use.' if eligible
                           else 'Resolve incomplete source accounting or verification gates in the linked evidence before accepting conversion.')
    analysis = doc.get('analysis') or {}
    evidence = [
        {'label':'Source-to-target lineage and every line', 'file':'coverage.html'},
        {'label':'Exact metrics and blocker details', 'file':'metrics.json'},
        {'label':'Editable management slides', 'file':'management.pptx'},
        {'label':'Inspection and artifact hashes', 'file':'inspection.json'}]
    if 'analysis/source-analysis.json' in doc.get('artifacts', []):
        evidence.append({'label':'Frozen source analysis', 'file':'../../analysis/source-analysis.json'})
    result={
        'schema_version':1, 'process_id':doc['id'], 'process_name':doc.get('name',doc['id']),
        'status':status, 'demo':bool(doc.get('demo')), 'fixture_only':bool(doc.get('fixture_only')),
        'primary_report':PRIMARY_REPORT,
        'scope':{'source_files':count('source_inventory_files'), 'physical_lines':total,
                 'in_scope_lines':scope, 'excluded_lines':excluded, 'non_executable_lines':nonexecutable,
                 'applicable_lines':applicable},
        'progress':{'converted_lines':converted, 'blocked_lines':blocked, 'unverified_lines':unverified,
                    'verification_percent':round(100*converted/applicable,2) if applicable else None,
                    'denominator':DENOMINATOR, 'completion_eligible':eligible and status!='CANCELLED',
                    'open_blockers':len(doc.get('blockers',[]))},
        'before_after':[
            {'label':'Programs', 'before':count('source_programs'), 'after':count('target_python_programs'),
             'basis':'Selected COBOL programs → generated Python programs; generation alone does not establish verified conversion.'},
            {'label':'Code lines', 'before':count('source_code_loc'), 'after':count('target_program_code_loc'),
             'basis':'Selected source code LOC → generated program Python LOC; size comparison, not parity.'},
            {'label':'Business screens', 'before':count('source_bms_screens'), 'after':count('target_react_business_screens'),
             'basis':'BMS screens → target React business screens; workbench controls are excluded.'},
            {'label':'Copybooks', 'before':count('source_copybooks'), 'after':None,
             'basis':'Selected source copybooks; a separate verified target-layout count is not established.'},
            {'label':'Known rules', 'before':count('rules_documented'), 'after':count('rules_verified'),
             'basis':'Extracted documented rules → SME-confirmed and tested rules; this is not all possible legacy behavior.'},
            {'label':'Business REST APIs', 'before':None, 'after':count('target_business_rest_apis'),
             'basis':'Source API count is unknown; target count excludes workbench control endpoints.'},
            {'label':'Db2 table references', 'before':count('source_db2_table_references'), 'after':None,
             'basis':'Distinct source SQL references, not an estate inventory; target business-table mapping count is unknown.'}],
        'scope_unknowns':[label for key,label in (('source_cics_transactions','CICS transactions'),
                         ('source_vsam_files','VSAM files'),('inbound_interfaces','Inbound interfaces'),
                         ('outbound_interfaces','Outbound interfaces')) if m.get(key) is None],
        'next_actions':actions[:3], 'evidence':evidence,
        'evidence_basis':'SOURCE_DERIVED_EXPECTED', 'observed_mainframe_parity':False,
        'boundary':'Bounded local source-derived POC verification. Observed mainframe parity and production readiness are not established.',
        'lineage':{'manifest_hash':doc.get('manifest_hash'), 'source_snapshot':analysis.get('source_snapshot'),
                   'coverage_file':'coverage.html', 'metrics_file':'metrics.json'}}
    # Historical accepted reports reproduce their original model; new reports
    # carry their complete frozen estate table through a scalar metrics field.
    if 'estate_inventory_json' in m:
        inventory=json.loads(m['estate_inventory_json'])
        require(isinstance(inventory,dict) and inventory.get('schema_version')==1 and len(inventory.get('rows',[]))==8,
                'Executive inventory model is incomplete')
        result['inventory']=inventory
    if 'rule_inventory' in doc:
        result['rule_inventory']=doc['rule_inventory']
        result['evidence'].append({'label':'Rules by job/program and original versus modernized behavior', 'file':'rules.html'})
    if doc.get('factory_report'):result['evidence'].append({'label':'Factory capabilities and online transaction mappings','file':'factory.html'})
    if doc.get('economics_summary'):
        result['economics']=doc['economics_summary']
        result['evidence'].append({'label':'Pilot effort, AI usage and conditional estate forecast','file':'economics.html'})
    if 'logic_validation_json' in m:result['logic_validation']=json.loads(m['logic_validation_json'])
    if 'adapter_priorities_json' in m:result['adapter_priorities']=json.loads(m['adapter_priorities_json'])
    return result


def render_executive(model):
    """Self-contained printable overview; detailed artifacts remain behind disclosure."""
    esc = lambda value: html.escape(str(value), quote=True)
    number = lambda value: 'Unknown' if value is None else f'{value:,}'
    scope = model['scope']; progress = model['progress']
    percent = progress['verification_percent']
    percent_text = 'Unknown (no applicable lines)' if percent is None else f'{percent:g}%'
    badge = ' · Fictional test fixture' if model.get('fixture_only') else ' · Demonstration' if model.get('demo') else ''
    rows = ''.join('<tr><th scope="row">'+esc(row['label'])+'</th><td>'+esc(number(row['before']))+'</td><td>'+esc(number(row['after']))+'</td><td>'+esc(row['basis'])+'</td></tr>' for row in model['before_after'])
    cards = [('In scope',scope['in_scope_lines'],'physical source lines'),
             ('Converted and verified',progress['converted_lines'],f'of {number(scope["applicable_lines"])} applicable lines'),
             ('Blocked',progress['blocked_lines'],'applicable source lines'),
             ('Mapped, unverified',progress['unverified_lines'],'applicable source lines')]
    cards_html = ''.join('<article><h2>'+esc(label)+'</h2><strong>'+esc(number(value))+'</strong><p>'+esc(detail)+'</p></article>' for label,value,detail in cards)
    actions = ''.join('<li>'+esc(action)+'</li>' for action in model['next_actions'])
    unknowns = '<p class="boundary">Unknown scope: '+esc(', '.join(model.get('scope_unknowns',[])))+'.</p>' if model.get('scope_unknowns') else ''
    links = ''.join('<li><a href="'+esc(item['file'])+'">'+esc(item['label'])+'</a></li>' for item in model['evidence'])
    economics_html=''
    if model.get('economics'):
        e=model['economics']; val=lambda k:esc(e.get(k) if e.get(k) is not None else 'Unknown')
        economics_html='<h2>Pilot effort and scaling</h2><p>Recorded pilot effort: '+val('pilot_effort_hours')+' hours · service execution: '+val('service_hours')+' hours · one-time framework work: '+val('framework_hours')+' hours.</p><p>Conditional remaining effort: '+val('remaining_base_hours')+' hours · capacity weeks: '+val('capacity_base_weeks')+'. Measured as of '+val('as_of')+'. Unknown work and billing remain unknown. Forecast assumptions and sample coverage are in the effort report; this is not a delivery commitment.</p>'
    inventory_html=''
    inventory=model.get('inventory')
    if inventory:
        inventory_rows=''.join('<tr><th scope="row">'+esc(row['label'])+'</th><td>'+esc(number(row['baseline_count']))+'</td><td>'+esc(number(row['process_observed_count']))+'</td><td>'+esc(number(row['process_converted_count']))+'</td><td>'+esc(number(row['remaining_vs_baseline']))+'</td></tr>' for row in inventory['rows'])
        inventory_html='<h2>Estate baseline and process progress</h2><p>User-reported, unverified baseline: declared total '+esc(number(inventory['declared_total']))+' · eight-category sum '+esc(number(inventory['category_total']))+' · '+esc(number(inventory['unreconciled_count']))+' unreconciled. No assets are invented to close the difference.</p><table><thead><tr><th>Category</th><th>Baseline</th><th>Observed process</th><th>Converted process POC</th><th>Delta</th></tr></thead><tbody>'+inventory_rows+'</tbody></table><p class="boundary">Delta = declared baseline minus cumulative verified local POC assets. Baseline counts remain unverified; unknown process scope is not zero. '+esc(inventory['scope_boundary'])+'</p><p class="boundary">'+esc(inventory['availability_basis'])+'</p>'
    adapters=model.get('adapter_priorities',[])
    adapter_html=''
    if adapters:
        adapter_html='<h2>Required conversion adapters</h2><p>Unsupported syntax remains unresolved conversion work. Priority follows blocked-line volume; recognition and SME agreement alone do not implement an adapter.</p><ol>'+''.join('<li>'+esc(group['label'])+': '+esc(number(group['blocked_lines']))+' blocked lines across '+esc(number(group['source_files']))+' source files.</li>' for group in adapters)+'</ol>'
    rule_html=''
    if model.get('rule_inventory'):
        from .rule_inventory import render_rule_summary
        rule_html=render_rule_summary({**model['rule_inventory'],'rules':[],'requirements_comparison':{}})
    validation=model.get('logic_validation')
    validation_html=''
    if validation:
        validation_html='<h2>Logic validation records</h2><p>Minimum '+esc(number(validation.get('minimum_distinct_records_per_logic')))+' distinct valid source-predicate input states per supported logic item. '+esc(number(validation.get('logic_meeting_minimum')))+' of '+esc(number(validation.get('known_supported_logic',validation.get('applicable_logic_count'))))+' known items meet the minimum; '+esc(number(validation.get('known_logic_missing_minimum')))+' do not. Unknown legacy logic count: Unknown.</p><p class="boundary">Duplicate records and unused-field padding do not count. Unsupported behavior and cross-file/native I/O gaps remain unresolved. Finite synthetic tests do not establish complete conversion or observed mainframe parity.</p>'
    if validation and validation.get('fixture_contract_version')==5:
        validation_html+='<p>Base floor: 64 randomized distinct source states. Recorded source risks require 128 states for '+esc(number(validation.get('risk_qualified_logic')))+' logic items. Each reachable decision outcome, boundary, invalid-input guard and actual target mutation also needs evidence; counts cannot replace these obligations.</p>'
    if validation and validation.get('fixture_contract_version') in (4,5):
        validation_html+='<p>Recorded random seed: '+esc(str(validation.get('seed','Unknown')))+' · Executed generated unit tests: '+esc(number(validation.get('unit_test_count')))+' · Job integration cases: '+esc(number(validation.get('job_cases')))+'.</p>'
    return '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Executive conversion report · '''+esc(model['process_id'])+'''</title>
<style>body{margin:0;background:#f4f0ed;color:#3b3331;font:16px/1.5 system-ui,sans-serif}main{max-width:1000px;margin:32px auto;padding:32px;background:white;border-radius:12px;border-top:6px solid #d71e28}h1{font-size:30px;line-height:1.2;margin:8px 0;overflow-wrap:anywhere}h2{font-size:18px}p{margin:8px 0}.muted{color:#615853}.status{font-weight:650}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:24px 0}.cards article{padding:16px;background:#f4f0ed;border-radius:8px}.cards h2{font-size:14px;margin:0}.cards strong{font-size:32px}.cards p{font-size:13px}table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:10px;border-bottom:1px solid #ded6d0}td:last-child{font-size:13px}a{color:#b51620;display:inline-flex;align-items:center;min-height:44px}a:focus-visible,summary:focus-visible{outline:3px solid #ffcd41;outline-offset:3px}thead{background:#ffcd41}details{margin-top:24px;padding:16px;background:#f4f0ed}summary{cursor:pointer;font-weight:650;min-height:44px;display:list-item;align-content:center}.boundary{font-size:13px;margin-top:22px}@media(max-width:650px){main{margin:0;padding:20px}.cards{grid-template-columns:repeat(2,1fr)}table{font-size:13px}th,td{padding:6px}}@media print{body{background:white}main{margin:0;padding:0;max-width:none}.cards article,details{break-inside:avoid}h2{break-after:avoid}}</style></head><body><main>
<p class="muted">Executive conversion report'''+esc(badge)+'''</p>
<h1>'''+esc(model['process_name'])+'''</h1><p class="status">'''+esc(model['status'].replace('_',' '))+''' · '''+esc(model['process_id'])+'''</p>
<div class="cards">'''+cards_html+'''</div>
<p><strong>Applicable-line verification: '''+esc(percent_text)+'''</strong> · '''+esc(number(progress['converted_lines']))+''' / '''+esc(number(scope['applicable_lines']))+''' lines.</p>
<p class="muted">'''+esc(number(scope['source_files']))+''' exported files · '''+esc(number(scope['physical_lines']))+''' physical lines · '''+esc(number(scope['excluded_lines']))+''' excluded · '''+esc(number(scope['non_executable_lines']))+''' non-executable.</p>
<p class="boundary">'''+esc(progress['denominator'])+'''</p>
'''+inventory_html+economics_html+'''<h2>Before → after</h2><table><thead><tr><th>Measure</th><th>Before</th><th>After</th><th>What it means</th></tr></thead><tbody>'''+rows+'''</tbody></table>'''+unknowns+'''
'''+rule_html+validation_html+adapter_html+'''<h2>Next actions</h2><ol>'''+actions+'''</ol>
<p class="boundary">'''+esc(model['boundary'])+'''</p>
<details><summary>Supporting evidence and slides</summary><ul>'''+links+'''</ul><p>Frozen source, target spans, test witnesses and reasons are available through the lineage report. Issued evidence is preserved by report version.</p></details>
</main></body></html>'''


class _Inspection(HTMLParser):
    def __init__(self):
        super().__init__(); self.links=[]; self.headings=0; self.details=0; self.unsafe=False
    def handle_starttag(self, tag, attrs):
        values=dict(attrs)
        if tag == 'a': self.links.append(values.get('href'))
        if tag == 'h1': self.headings+=1
        if tag == 'details': self.details+=1; self.unsafe |= 'open' in values
        self.unsafe |= tag in ('script','iframe','object','embed','form') or any(k.startswith('on') for k in values)


def inspect_executive(text, model):
    parsed=_Inspection(); parsed.feed(text)
    require(parsed.headings==1 and parsed.details==1 and not parsed.unsafe,
            'Executive HTML structure or collapsed disclosure inspection failed')
    allowed_links=EVIDENCE_FILES
    require(all(link in allowed_links for link in parsed.links), 'Executive evidence destination is unsafe or unsupported')
    require(parsed.links == [item['file'] for item in model['evidence']], 'Executive evidence links differ from the frozen model')
    require(html.escape(model['process_id'],quote=True) in text and html.escape(model['status'].replace('_',' '),quote=True) in text,
            'Executive report identity or status is missing')
    require(text == render_executive(model), 'Executive HTML values differ from the frozen metric model')
    return True


def executive_report_relative(doc):
    if not doc.get('report_verified'): return None
    hashes=doc.get('report_hashes') or {}
    candidates=[name for name in hashes if re.fullmatch(r'reports/report-[0-9]{4,}/executive-report\.html',name)
                and name in doc.get('artifacts',[]) and re.fullmatch(r'[a-f0-9]{64}',str(hashes[name]))]
    return candidates[0] if len(candidates)==1 else None


def accepted_executive(coordinator, doc):
    """Read only the accepted generation, verifying artifact bytes through Coordinator."""
    relative=executive_report_relative(doc)
    if relative is None: return {'executive':None, 'executive_report':None}
    metrics_path=str(PurePosixPath(relative).parent/'metrics.json')
    require(metrics_path in doc.get('report_hashes',{}) and metrics_path in doc.get('artifacts',[]),
            'Executive metrics are missing from the accepted report baseline')
    report_path=coordinator.artifact(doc['id'],relative)
    frozen=json.loads(coordinator.artifact(doc['id'],metrics_path).read_text(encoding='utf-8'))
    model=frozen.get('executive')
    require(isinstance(model,dict) and model.get('schema_version')==1 and model.get('process_id')==doc['id']
            and model.get('primary_report')==PRIMARY_REPORT, 'Accepted executive summary is missing or inconsistent')
    context=frozen.get('executive_context')
    require(isinstance(context,dict), 'Accepted executive context is missing')
    require(executive_summary(context,frozen.get('metrics') or {}) == model,
            'Accepted executive summary differs from its frozen metrics or context')
    inspect_executive(report_path.read_text(encoding='utf-8'),model)
    return {'executive':model, 'executive_report':relative}
