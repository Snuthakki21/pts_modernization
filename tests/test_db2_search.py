"""Fictional DB-API fixtures exercise discovery, contents, gaps and resumability."""
import tempfile
import unittest
from pathlib import Path
from workbench.db2_discovery import SearchStore, quoted


class Cursor:
    def __init__(self, owner): self.owner=owner; self.rows=[]; self.description=[]
    def execute(self, sql, *params):
        self.owner.sql.append((sql, params))
        if 'SYSIBM"."LOCATIONS' in sql:
            self.description=[('LOCATION',)]
            self.rows=[('REMOTE',)] if not params[0] else []
        elif 'SYSIBM"."SYSTABLES' in sql:
            self.description=[('CREATOR',),('NAME',),('TYPE',)]
            self.rows=([('OTHER', 'Hidden Table', 'T')] if '"REMOTE".' in sql else [('A','Denied','T'),('B','Records','T')]) if not params[0] else []
        elif '"Denied"' in sql: raise Exception('42501', 'SECRET driver text')
        else:
            self.description=[('TEXT',),('NUMBER',)]
            self.rows=[('needle at remote' if 'REMOTE' in sql else 'needle here', 7), ('nothing', 8)]
        return self
    def fetchmany(self, count):
        rows=self.rows[:count]; self.rows=self.rows[count:]; return rows
    def close(self): pass


class Connection:
    def __init__(self, sql): self.sql=sql
    def cursor(self): return Cursor(self)
    def close(self): pass


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.sql=[]; self.store=SearchStore(Path(self.tmp.name)/'search',lambda:Connection(self.sql),lambda:500000)
        self.addCleanup(self.store.close)
    def finish(self, token):
        for _ in range(100):
            result=self.store.advance(token, 50)
            if result['status']!='RUNNING': return result
        self.fail('Search never finished')
    def test_remote_unknown_schema_content_and_denial_are_accounted(self):
        result=self.finish(self.store.start('needle')['search_id'])
        self.assertEqual(result['status'],'PARTIAL')
        token=result['search_id']; matches=self.store.results(token)['rows']
        self.assertEqual({x['location'] for x in matches if x['kind']=='content'},{'', 'REMOTE'})
        outcomes=self.store.results(token,kind='objects')['rows']
        self.assertTrue(any(x['reason']=='permission_denied' for x in outcomes))
        self.assertNotIn('SECRET',str(outcomes))
        self.assertTrue(all(sql.startswith('SELECT ') for sql,_ in self.sql))
        self.assertTrue(all('WITH UR' in sql for sql,_ in self.sql))
    def test_query_is_literal_never_interpolated_into_sql(self):
        query="x'); DELETE FROM B.Records;--"
        self.finish(self.store.start(query)['search_id'])
        self.assertTrue(all(query not in sql for sql,_ in self.sql))
    def test_row_cap_partial_even_if_table_exactly_cap(self):
        self.store.row_limit=lambda:1
        result=self.finish(self.store.start('needle')['search_id'])
        self.assertEqual(result['status'],'PARTIAL')
        rows=self.store.results(result['search_id'],kind='objects')['rows']
        self.assertTrue(any(r['reason']=='row_budget' and r['rows_read']==1 for r in rows))
    def test_cancel_and_restart_do_not_restart_completed_objects(self):
        token=self.store.start('needle')['search_id']; self.store.advance(token,1)
        self.store.cancel(token)
        self.assertEqual(self.store.advance(token)['status'],'CANCELLED')
        self.store.close()
        again=SearchStore(Path(self.tmp.name)/'search',lambda:Connection(self.sql),lambda:500000)
        try: self.assertEqual(again.status(token)['status'],'CANCELLED')
        finally: again.close()
    def test_identifiers_and_tokens(self):
        self.assertEqual(quoted('a"b'), '"a""b"')
        with self.assertRaises(ValueError): quoted('a\x00b')
        with self.assertRaises(ValueError): self.store.status('../secret')
        with self.assertRaises(ValueError): self.store.start('')
    def test_page_offset_has_no_duplicate_matches(self):
        token=self.finish(self.store.start('needle')['search_id'])['search_id']
        page=self.store.results(token,limit=1); following=self.store.results(token,after=page['next_after'],limit=1)
        self.assertNotEqual(page['rows'],following['rows'])

    def test_rejects_overlong_original_query_and_preserves_journal(self):
        from workbench.connectors import validate_read_operation
        query=' '*1000000+'needle'
        before=self.store.path.stat().st_size
        with self.assertRaises(ValueError):self.store.start(query)
        with self.assertRaises(ValueError):validate_read_operation('db2_search_start',{'query':query})
        self.assertEqual(self.store.path.stat().st_size,before)

    def test_only_one_journal_writer_and_cleanup_allows_new_owner(self):
        with self.assertRaisesRegex(ValueError,'writer'):
            SearchStore(self.store.root,lambda:Connection(self.sql),lambda:500000)
        self.store.close()
        again=SearchStore(self.store.root,lambda:Connection(self.sql),lambda:500000)
        again.close()

    def test_empty_table_column_names_are_searchable(self):
        from unittest.mock import patch
        original=Cursor.execute
        def empty(cursor,sql,*params):
            original(cursor,sql,*params)
            if 'SYSIBM' not in sql:
                cursor.description=[('NEEDLE_COLUMN',)];cursor.rows=[]
            return cursor
        with patch.object(Cursor,'execute',empty):
            token=self.finish(self.store.start('needle')['search_id'])['search_id']
        rows=self.store.results(token)['rows']
        self.assertTrue(any(r['column']=='NEEDLE_COLUMN' and r['kind']=='metadata' for r in rows))

    def test_casefold_expansion_excerpt_contains_actual_match(self):
        from unittest.mock import patch
        original=Cursor.execute
        def unicode_row(cursor,sql,*params):
            original(cursor,sql,*params)
            if 'SYSIBM' not in sql:cursor.rows=[('ß'*200+'needle',7)]
            return cursor
        with patch.object(Cursor,'execute',unicode_row):
            token=self.finish(self.store.start('needle')['search_id'])['search_id']
        rows=self.store.results(token)['rows']
        self.assertTrue(all('needle' in r['excerpt'] for r in rows if r['kind']=='content'))

    def test_storage_bound_returns_explicit_partial_in_same_call(self):
        from unittest.mock import patch
        original=Cursor.execute
        def wide(cursor,sql,*params):
            original(cursor,sql,*params)
            if 'SYSIBM' not in sql:
                cursor.description=[('C'+str(i),) for i in range(300)]
                cursor.rows=[tuple('needle'+'x'*400 for _ in range(300)) for _ in range(10)]
            return cursor
        with patch.object(Cursor,'execute',wide),patch('workbench.db2_discovery.MAX_STATE_BYTES',65536):
            token=self.store.start('needle')['search_id']; result=self.finish(token)
        self.assertEqual(result['status'],'PARTIAL')
        self.assertLessEqual(self.store.path.stat().st_size,65536)
        self.assertTrue(any(r['reason']=='storage_budget' for r in self.store.results(token,kind='objects')['rows']))

    def test_expired_cursor_retains_partial_and_closes_resources(self):
        token=self.store.start('needle')['search_id'];self.store.advance(token,1)
        self.assertTrue(self.store.live)
        self.store.timer.cancel()
        for entry in self.store.live.values():entry['used']-=301
        self.store._expire()
        self.assertFalse(self.store.live)
        self.assertTrue(any(r['reason']=='cursor_expired' for r in self.store.results(token,kind='objects')['rows']))

    def test_failed_start_rolls_back_both_search_and_object_entries(self):
        from unittest.mock import patch
        from workbench.db2_discovery import StorageBudget
        original=self.store._add; calls=[]
        def fail_second(*args):
            calls.append(args)
            if len(calls)==2:raise StorageBudget('storage_budget')
            original(*args)
        with patch.object(self.store,'_add',side_effect=fail_second):
            with self.assertRaises(StorageBudget):self.store.start('needle')
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM searches').fetchone()[0],0)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM objects').fetchone()[0],0)

    def test_malformed_catalog_shape_and_types_remain_partial(self):
        from unittest.mock import patch
        original=Cursor.execute
        for malformed in ('extra_column','numeric_location'):
            def bad(cursor,sql,*params):
                original(cursor,sql,*params)
                if 'LOCATIONS' in sql:
                    cursor.description=[('LOCATION',),('EXTRA',)] if malformed=='extra_column' else [('LOCATION',)]
                    cursor.rows=[('REMOTE','discarded')] if malformed=='extra_column' else [(123,)]
                return cursor
            with patch.object(Cursor,'execute',bad):
                token=self.store.start('needle')['search_id'];result=self.finish(token)
            self.assertEqual(result['status'],'PARTIAL')
            outcomes=self.store.results(token,kind='objects')['rows']
            self.assertTrue(any(r['kind']=='locations' and r['reason']=='read_failed' for r in outcomes))
            self.assertFalse(any(r['location'] for r in outcomes))


if __name__=='__main__': unittest.main()
