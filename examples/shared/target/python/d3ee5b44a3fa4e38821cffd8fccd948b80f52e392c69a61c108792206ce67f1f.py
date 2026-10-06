# Generated from source SHA256 1b86b3b54531ecac8dcf7d8357d39532ec2bb02af7cb3b24dc9b6871b343899a
# Evidence class: SOURCE_DERIVED_EXPECTED
# Semantic/dependency SHA256 f50ed334f61057aadb73aaa1d81dac109c03526f9e6b5001fb886150d98ed27f
def run_program(record):
    row = dict(record)
    trace = []
    if (row['AGE'] >= 18):
        row['DECISION'] = 'Y'
        trace.append({'rule_id': 'ELIGIBLE_R001', 'branch': True, 'source_refs': ['ELIGIBLE.cbl:7-11']})
    else:
        row['DECISION'] = 'N'
        trace.append({'rule_id': 'ELIGIBLE_R001', 'branch': False, 'source_refs': ['ELIGIBLE.cbl:7-11']})
    if (row['ACTIVE'] == 'N'):
        row['DECISION'] = 'N'
        trace.append({'rule_id': 'ELIGIBLE_R002', 'branch': True, 'source_refs': ['ELIGIBLE.cbl:12-16']})
    else:
        trace.append({'rule_id': 'ELIGIBLE_R002', 'branch': False, 'source_refs': ['ELIGIBLE.cbl:12-16']})
    if (row['CUSTOMER-ID'] != row['REF-CUSTOMER-ID']):
        row['DECISION'] = 'N'
        trace.append({'rule_id': 'ELIGIBLE_R003', 'branch': True, 'source_refs': ['ELIGIBLE.cbl:17-21']})
    else:
        trace.append({'rule_id': 'ELIGIBLE_R003', 'branch': False, 'source_refs': ['ELIGIBLE.cbl:17-21']})
    if (row['AMOUNT'] > 50000):
        row['DECISION'] = 'R'
        trace.append({'rule_id': 'ELIGIBLE_R004', 'branch': True, 'source_refs': ['ELIGIBLE.cbl:22-26']})
    else:
        trace.append({'rule_id': 'ELIGIBLE_R004', 'branch': False, 'source_refs': ['ELIGIBLE.cbl:22-26']})
    return {'input_status': 'ACCEPT_INPUT', 'record': row, 'trace': trace, 'return_code': 0}
