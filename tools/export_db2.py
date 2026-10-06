#!/usr/bin/env python3
"""Explicit bounded read-only export; never invoked during lineage discovery."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workbench.connectors import Db2MCP,export_table_rows
from workbench.domain import ValidationError,require,safe_path
from workbench.layout import require_layout


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',default=str(Path.cwd()));parser.add_argument('--schema',required=True)
    parser.add_argument('--table',required=True);parser.add_argument('--max-rows',type=int,default=1000)
    parser.add_argument('--page-size',type=int,default=100);args=parser.parse_args(argv)
    try:
        require_layout(args.workspace);require(os.environ.get('WB_DB2_MCP_URL'),'Configure the approved read-only gateway')
        client=Db2MCP(os.environ['WB_DB2_MCP_URL'],os.environ.get('WB_DB2_MCP_TOKEN',''));client.initialize()
        filename=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex+'.ndjson'
        output=safe_path(args.workspace,'.migration/db2-exports/'+filename)
        result=export_table_rows(client,args.schema,args.table,output,args.max_rows,args.page_size)
        print(json.dumps(result,indent=2));return 0 if result['status']=='READ_COMPLETED' else 3
    except (ValidationError,OSError):
        print(json.dumps({'status':'BLOCKED','message':'Typed table export failed. Check the private gateway, account, exact table and bounds locally.'}));return 2


if __name__=='__main__':raise SystemExit(main())
