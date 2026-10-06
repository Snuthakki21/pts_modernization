"""Compact, provenance-bound approved knowledge; user Markdown is evidence only."""
import json
from pathlib import Path
import tempfile
from .domain import sha, encode, decode, atomic_json, require, safe_path
from .ledger import now
from .review import read_answers


def update_knowledge(ledger, process):
    """Publish only preserved human evidence; each review retains its provenance.

    SQLite is canonical. Projection writes can be replayed after an interruption,
    but an existing interpretation is never replaced with conflicting content.
    """
    with ledger.lock:
        persisted=ledger.get(process['id'])
        require(persisted['packet_issued'] and persisted['packet_imported'],
                'Approved knowledge requires the consumed human SME return')
        require(process.get('answers')==persisted.get('answers') and
                process.get('packet_hash')==persisted['packet_hash'] and
                process.get('analysis')==persisted.get('analysis'),
                'Knowledge input differs from the preserved process evidence')
        root=safe_path(ledger.root,'processes/'+process['id'])
        packet_path=safe_path(root,'review/packet.json')
        packet_raw=packet_path.read_bytes();packet=decode(packet_raw)
        require(sha(packet_raw)==persisted.get('artifact_hashes',{}).get('review/packet.json') and
                packet.get('packet_hash')==persisted['packet_hash'] and packet.get('process_id')==process['id'] and
                packet.get('source_snapshot')==process['analysis']['source_snapshot'],
                'Knowledge packet provenance differs from the frozen process')
        raw=safe_path(root,'input/sme-return.xlsx').read_bytes()
        require(sha(raw)==process['answers'].get('return_hash'),'Preserved SME return changed')
        require(read_answers(raw,packet,process['answers'].get('reviewer',''))==process['answers'],
                'Knowledge answers differ from the preserved human return')
        analysis_raw=safe_path(root,'analysis/source-analysis.json').read_bytes()
        require(sha(analysis_raw)==persisted.get('artifact_hashes',{}).get('analysis/source-analysis.json') and
                decode(analysis_raw)==process['analysis'],'Knowledge rules differ from frozen source analysis')
        records_path=safe_path(ledger.root,'knowledge/records.json')
        index_path=safe_path(ledger.root,'knowledge/INDEX.md')
        answers=process['answers']['items']
        with ledger.db:
            for rule in process['analysis']['rules']:
                answer=answers.get(rule['id'],{})
                if answer.get('answer')!='Yes' or answer.get('correction'):continue
                provenance={'source_snapshot':process['analysis']['source_snapshot'],'process_id':process['id'],
                            'rule_id':rule['id'],'packet_hash':process['packet_hash'],
                            'return_hash':process['answers']['return_hash']}
                key=sha(encode(provenance))
                doc={'id':key,'rule_id':rule['id'],'statement':rule['plain'],
                     'applicability':{'source_snapshot':provenance['source_snapshot'],'process_id':process['id']},
                     'source_refs':rule['source_refs'],'reviewer':answer['reviewer'],'packet_hash':process['packet_hash'],
                     'return_hash':provenance['return_hash'],
                     'confidence':'SME confirmed interpretation; target verification is separate','supersedes':[]}
                text=encode(doc).decode()
                existing=ledger.db.execute('SELECT document FROM knowledge WHERE id=?',(key,)).fetchone()
                require(existing is None or existing[0]==text,'Knowledge conflicts with preserved historical provenance')
                ledger.db.execute('INSERT OR IGNORE INTO knowledge VALUES(?,?,?)',(key,text,now()))
            rows=ledger.db.execute('SELECT document FROM knowledge ORDER BY id').fetchall()
        records=[json.loads(row[0]) for row in rows]
        atomic_json(records_path,records)
        index='# SME-confirmed knowledge index\n\n'+str(len(records))+' provenance-bound interpretations; target verification is separate. Canonical structured records: records.json.\n\n'+'\n'.join('- '+r['rule_id']+': '+r['statement'].replace('\n',' ') for r in records)
        staging=safe_path(ledger.root,'.implementation/tmp');staging.mkdir(parents=True,exist_ok=True)
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=staging,prefix='knowledge-index-',delete=False) as out:
                temporary=Path(out.name);out.write(index)
            temporary.replace(index_path)
        finally:
            if temporary is not None:temporary.unlink(missing_ok=True)
        return len(records)
