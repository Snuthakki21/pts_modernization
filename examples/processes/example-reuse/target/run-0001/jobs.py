# Generated ordered orchestration. Program implementations are shared and version-pinned.
def run_job_refjob(context, programs):
    results = []
    previous_rc = 0
    if True:
        result = programs['ELIGIBLE'](context['record'])
        results.append({'step': 'CHECK', 'version': 'd3ee5b44a3fa4e38821cffd8fccd948b80f52e392c69a61c108792206ce67f1f'} | result)
        previous_rc = result['return_code']
        context['record'] = result['record']
    else:
        results.append({'step': 'CHECK', 'status': 'SKIPPED'})
    return results
def run_process(context, programs):
    results = {}
    results['REFJOB'] = run_job_refjob(context, programs)
    return results
