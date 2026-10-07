#!/usr/bin/env python3
"""Check shared factory interfaces and executable documentation contracts."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from workbench.process_context import MAX_CONTEXT_FILES, MAX_CONTEXT_BYTES
from workbench.factory import CAPABILITIES, STAGES
from workbench.api import create_app
from tools.workbench_mcp import TOOLS, WorkflowBridge
from workbench.domain import ValidationError


def check(root):
    root=Path(root);issues=[]
    for name in ('START_HERE.md','docs/TECHNICAL_REFERENCE.md','knowledge/README.md'):
        text=(root/name).read_text(encoding='utf-8')
        if 'up to 16 KB' in text or 'maximum 16 KB for automatic ingestion' in text:issues.append(name+': obsolete context limit')
        if str(MAX_CONTEXT_FILES) not in text or str(MAX_CONTEXT_BYTES//(1024*1024))+' MiB' not in text:issues.append(name+': current context bounds missing')
    if set(TOOLS) != {'workbench_retrieval_task'}:issues.append('Copilot MCP must expose only the retrieval request')
    if set(WorkflowBridge(role='discovery').tools) != {'workbench_retrieval_task'}:issues.append('Legacy discovery alias restores forbidden tools')
    try:WorkflowBridge(role='development')
    except ValidationError:pass
    else:issues.append('Claude development MCP integration must be rejected')
    claude=json.loads((root/'examples/claude-mcp.json').read_text())
    if claude != {'mcpServers':{}}:issues.append('Claude template must configure no MCP servers')
    copilot=json.loads((root/'examples/mcp.json').read_text())
    if copilot['servers']['workbench']['args'][-2:]!=['--role','retrieval']:issues.append('Copilot template must select retrieval')
    # The route must exist in the real running API, not just the advertised schema.
    import tempfile
    scratch=root/'.implementation/tmp';scratch.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as temp:
        app=create_app(temp)
        try:
            paths={route.path for route in app.routes}
            for route in ('/api/process/{pid}/retrieval','/api/process/{pid}/local-agent','/api/process/{pid}/local-agent/{action}'):
                if route not in paths:issues.append('Local-file handoff HTTP surface absent: '+route)
            if '/api/process/{pid}/factory' not in {route.path for route in app.routes}:issues.append('HTTP factory surface absent')
        finally:app.state.coordinator.close()
    for name in ('mainframe-discovery','mainframe-semantics','mainframe-target','mainframe-assurance'):
        if not (root/'.claude/skills'/name/'SKILL.md').is_file():issues.append('Shared mainframe skill missing: '+name)
    return {'passed':not issues,'issues':issues,'capability_domains':len(CAPABILITIES),'workflow_stages':list(STAGES),'scope':'Interface/documentation consistency; no mainframe support or connectivity certification'}

if __name__=='__main__':
    result=check(Path(__file__).resolve().parents[1]);print(json.dumps(result,indent=2));raise SystemExit(0 if result['passed'] else 1)
