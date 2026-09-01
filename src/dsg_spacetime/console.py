from __future__ import annotations

import ipaddress
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from .mcp_stdio import MAX_MESSAGE_BYTES, PROTOCOL_VERSION, StdioMcpServer, load_runtime


CONSOLE_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DSG ONE — Spacetime Console</title>
<style>
:root{color-scheme:dark;--bg:#050914;--panel:#0d162a;--line:#223656;--ink:#e8eefc;--muted:#93a6c8;--cyan:#38e0d0;--green:#3ddc97;--amber:#f5b544;--red:#fb7185;--blue:#4d8dff}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 80% 0,#12234b 0,transparent 35%),var(--bg);color:var(--ink);font:14px system-ui,-apple-system,Segoe UI,sans-serif}.shell{max-width:1180px;margin:auto;padding:28px 18px 60px}header{display:flex;gap:18px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin-bottom:22px}h1{font-size:28px;margin:0}header p{margin:6px 0 0;color:var(--muted)}.status{padding:8px 12px;border:1px solid var(--line);border-radius:999px;color:var(--muted)}.status.ok{color:var(--green);border-color:#245d4a}.grid{display:grid;grid-template-columns:1.1fr .9fr;gap:18px}.panel{background:linear-gradient(160deg,#101a31dd,#0a1122ee);border:1px solid var(--line);border-radius:16px;padding:18px}.panel h2{font-size:15px;margin:0 0 14px}.flow{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin:12px 0 18px}.step{border:1px solid var(--line);border-radius:12px;padding:12px 8px;text-align:center;color:var(--muted)}.step.active{border-color:var(--blue);color:#dbe8ff}.step.pass{border-color:#245d4a;color:var(--green)}.step.fail{border-color:#743044;color:var(--red)}label{display:block;color:var(--muted);font-size:12px;margin:12px 0 5px}input,select,textarea{width:100%;background:#070d1a;border:1px solid var(--line);border-radius:10px;padding:10px;color:var(--ink)}textarea{min-height:100px;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;resize:vertical}.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}.btn{margin-top:14px;border:0;border-radius:10px;padding:11px 15px;background:linear-gradient(135deg,var(--blue),#8b7cf6);color:white;font-weight:700;cursor:pointer}.btn:disabled{opacity:.45;cursor:not-allowed}.cards{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}.card{border:1px solid var(--line);border-radius:12px;padding:12px;min-height:86px}.card b{display:block;font-size:11px;color:var(--muted);margin-bottom:6px;text-transform:uppercase;letter-spacing:.08em}.card strong{font-size:18px}.card small{display:block;margin-top:5px;color:var(--muted);overflow-wrap:anywhere}pre{margin:0;white-space:pre-wrap;word-break:break-word;background:#050a13;border:1px solid var(--line);border-radius:12px;padding:12px;min-height:260px;max-height:500px;overflow:auto;font:11px ui-monospace,SFMono-Regular,Consolas,monospace}.boundary{margin-top:18px;color:var(--muted);font-size:12px;border-left:3px solid var(--cyan);padding-left:10px}@media(max-width:820px){.grid{grid-template-columns:1fr}.flow{grid-template-columns:1fr}.row,.cards{grid-template-columns:1fr}}
</style>
</head>
<body><div class="shell"><header><div><h1>DSG ONE · Spacetime Console</h1><p>Customer-hosted operational UI over the same governed DSG Spacetime runtime.</p></div><div id="status" class="status">CONNECTING</div></header><div class="grid"><section class="panel"><h2>Run a governed Route</h2><div class="flow"><div class="step" data-step="discover">Discover</div><div class="step" data-step="compose">Compose</div><div class="step" data-step="govern">Govern</div><div class="step" data-step="execute">Execute</div><div class="step" data-step="prove">Prove</div></div><label>Route</label><select id="route"></select><div class="row"><div><label>Agent ID</label><input id="agent" value="dsg-one-console"></div><div><label>Principal</label><input id="principal" value="customer:operator"></div></div><label>Approval ID (required only for approval-gated Routes)</label><input id="approval" placeholder="optional"><label>Payload JSON</label><textarea id="payload">{"value":"console-smoke"}</textarea><button id="run" class="btn" disabled>Run All Flows</button><div class="boundary">The browser does not authorize itself. Compose remains untrusted until bound; execution still passes entitlement, plan, Route, approval and evidence gates in DSG Spacetime.</div></section><section class="panel"><h2>Runtime truth</h2><div class="cards"><div class="card"><b>Protocol</b><strong id="protocol">—</strong><small>MCP</small></div><div class="card"><b>Deployment</b><strong id="deployment">—</strong><small>local entitlement boundary</small></div><div class="card"><b>Nodes</b><strong id="nodes">—</strong><small>approved capability boundaries</small></div><div class="card"><b>Routes</b><strong id="routes">—</strong><small>governed paths</small></div><div class="card"><b>Decision</b><strong id="decision">PENDING</strong><small id="reason">No execution yet</small></div><div class="card"><b>Evidence</b><strong id="evidence">PENDING</strong><small id="records">No proof yet</small></div></div><h2 style="margin-top:18px">Execution transcript</h2><pre id="log">Waiting for runtime…</pre></section></div></div>
<script>
const $=id=>document.getElementById(id), log=$('log'); let catalog=null, seq=0;
function write(label,data){log.textContent+=`\n\n${label}\n${JSON.stringify(data,null,2)}`;log.scrollTop=log.scrollHeight}
function step(name,state){const el=document.querySelector(`[data-step="${name}"]`);el.className=`step ${state||''}`}
async function rpc(method,params){seq++;const response=await fetch('./api/mcp',{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json'},body:JSON.stringify({jsonrpc:'2.0',id:seq,method,params})});const body=await response.json();if(!response.ok||body.error)throw new Error(body.error?.message||`HTTP ${response.status}`);return body.result}
function structured(result){if(result?.isError)throw new Error(JSON.stringify(result.structuredContent||result));return result?.structuredContent||result}
async function boot(){try{const status=await fetch('./api/status').then(r=>r.json());catalog=await fetch('./api/catalog').then(r=>r.json());$('status').textContent=status.status;$('status').classList.add('ok');$('protocol').textContent=status.protocol_version;$('deployment').textContent=status.deployment_id;$('nodes').textContent=catalog.nodes.length;$('routes').textContent=catalog.routes.length;const select=$('route');catalog.routes.forEach(r=>{const o=document.createElement('option');o.value=r.route_id;o.textContent=`${r.source_node} → ${r.target_node} · ${r.capability}${r.approval_required?' · approval':''}`;select.appendChild(o)});$('run').disabled=!catalog.routes.length;log.textContent='Runtime connected. Select a Route and click Run All Flows.'}catch(e){$('status').textContent='BLOCKED';log.textContent=`Console could not initialize: ${e.message}`}}
$('run').addEventListener('click',async()=>{const button=$('run');button.disabled=true;document.querySelectorAll('.step').forEach(x=>x.className='step');$('decision').textContent='RUNNING';$('evidence').textContent='PENDING';log.textContent='';try{const route=catalog.routes.find(r=>r.route_id===$('route').value);if(!route)throw new Error('Select a valid Route');let payload;try{payload=JSON.parse($('payload').value)}catch(e){throw new Error('Payload must be valid JSON')}
step('discover','active');write('initialize',await rpc('initialize',{}));write('tools/list',await rpc('tools/list',{}));const discovered=structured(await rpc('tools/call',{name:'spacetime_discover',arguments:{capabilities:[route.capability]}}));write('discover',discovered);step('discover','pass');
step('compose','active');const agent={agent_id:$('agent').value.trim()||'dsg-one-console',principal:$('principal').value.trim()||'customer:operator'};const planId=`console-${Date.now()}-${Math.random().toString(16).slice(2)}`;const composed=structured(await rpc('tools/call',{name:'spacetime_compose',arguments:{plan_id:planId,intent:`Execute ${route.capability} through ${route.route_id}`,participants:[agent],routes:[{source_node:route.source_node,target_node:route.target_node,capability:route.capability}]}}));write('compose',composed);step('compose','pass');
step('govern','active');if(composed.verdict!=='BOUND')throw new Error(`Plan not bound: ${composed.reason||'unknown'}`);step('govern','pass');
step('execute','active');const args={plan_id:planId,plan_hash:composed.plan_hash,route_id:route.route_id,agent,payload};const approval=$('approval').value.trim();if(approval)args.approval_id=approval;const executed=structured(await rpc('tools/call',{name:'spacetime_execute',arguments:args}));write('execute',executed);$('decision').textContent=executed.decision?.verdict||executed.verdict||'UNKNOWN';$('reason').textContent=executed.decision?.reason||executed.reason||'—';step('execute',executed.decision?.verdict==='ALLOW'?'pass':'fail');if(executed.decision?.verdict!=='ALLOW')throw new Error(`Execution ${executed.decision?.verdict||'BLOCK'}: ${executed.decision?.reason||'rejected'}`);
step('prove','active');const verified=structured(await rpc('tools/call',{name:'spacetime_verify_evidence',arguments:{}}));write('verify evidence',verified);$('evidence').textContent=verified.valid?'VERIFIED':'FAIL';$('records').textContent=`${verified.records} evidence record(s)`;step('prove',verified.valid?'pass':'fail');if(!verified.valid)throw new Error('Evidence verification failed')
}catch(e){write('BLOCKED',{error:e.message});document.querySelectorAll('.step.active').forEach(x=>x.classList.add('fail'));if($('decision').textContent==='RUNNING'){$('decision').textContent='BLOCK';$('reason').textContent=e.message}}finally{button.disabled=!catalog?.routes?.length}});boot();
</script></body></html>'''


def _require_loopback(host: str) -> None:
    normalized = host.strip().lower()
    if normalized == "localhost":
        return
    try:
        if ipaddress.ip_address(normalized).is_loopback:
            return
    except ValueError:
        pass
    raise ValueError("CONSOLE_HOST_MUST_BE_LOOPBACK")


def _hostname_is_loopback(value: str | None) -> bool:
    if not value:
        return False
    candidate = value.strip()
    try:
        parsed = urlsplit(candidate if "://" in candidate else f"http://{candidate}")
    except ValueError:
        return False
    if parsed.hostname is None:
        return False
    try:
        _require_loopback(parsed.hostname)
    except ValueError:
        return False
    return True


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def create_console_server(
    *,
    config_path: str,
    entitlement_path: str,
    evidence_path: str,
    host: str = "127.0.0.1",
    port: int = 8765,
    public_key_b64: str | None = None,
) -> ThreadingHTTPServer:
    _require_loopback(host)
    runtime, composer, evidence = load_runtime(
        config_path=config_path,
        entitlement_path=entitlement_path,
        evidence_path=evidence_path,
        public_key_b64=public_key_b64,
    )
    mcp = StdioMcpServer(runtime, composer, evidence)

    class ConsoleHandler(BaseHTTPRequestHandler):
        server_version = "DSGSpacetimeConsole/0.1"

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: Any) -> None:
            self._send(status, _json_bytes(payload), "application/json; charset=utf-8")

        def _request_origin_allowed(self, *, require_json: bool = False) -> bool:
            if not _hostname_is_loopback(self.headers.get("Host")):
                self._json(403, {"error": "CONSOLE_HOST_BLOCKED"})
                return False
            origin = self.headers.get("Origin")
            if origin and not _hostname_is_loopback(origin):
                self._json(403, {"error": "CONSOLE_ORIGIN_BLOCKED"})
                return False
            if require_json:
                media_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if media_type != "application/json":
                    self._json(415, {"error": "APPLICATION_JSON_REQUIRED"})
                    return False
            return True

        def do_GET(self) -> None:
            if not self._request_origin_allowed():
                return
            path = self.path.split("?", 1)[0]
            if path in {"/", "/index.html"}:
                self._send(200, CONSOLE_HTML.encode("utf-8"), "text/html; charset=utf-8")
                return
            if path == "/api/status":
                self._json(
                    200,
                    {
                        "status": "READY",
                        "server": "dsg-spacetime",
                        "protocol_version": PROTOCOL_VERSION,
                        "deployment_id": runtime.deployment_id,
                    },
                )
                return
            if path == "/api/catalog":
                self._json(
                    200,
                    {
                        "nodes": [
                            {
                                "node_id": node.node_id,
                                "label": node.public_label,
                                "capabilities": sorted(node.capabilities),
                            }
                            for node in sorted(runtime.nodes.values(), key=lambda item: item.node_id)
                        ],
                        "routes": [
                            {
                                "route_id": route.route_id,
                                "source_node": route.source_node,
                                "target_node": route.target_node,
                                "capability": route.capability,
                                "risk": route.risk,
                                "approval_required": route.approval_required,
                            }
                            for route in sorted(runtime.routes.values(), key=lambda item: item.route_id)
                        ],
                    },
                )
                return
            self._json(404, {"error": "NOT_FOUND"})

        def do_POST(self) -> None:
            if not self._request_origin_allowed(require_json=True):
                return
            if self.path.split("?", 1)[0] != "/api/mcp":
                self._json(404, {"error": "NOT_FOUND"})
                return
            raw_length = self.headers.get("Content-Length", "")
            try:
                length = int(raw_length)
            except ValueError:
                self._json(400, {"error": "INVALID_CONTENT_LENGTH"})
                return
            if length <= 0 or length > MAX_MESSAGE_BYTES:
                self._json(413, {"error": "REQUEST_TOO_LARGE"})
                return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("request must be object")
                result = mcp.handle(payload)
                if result is None:
                    self._json(202, {})
                else:
                    self._json(200, result)
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
                self._json(
                    400,
                    {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
                )

    return ThreadingHTTPServer((host, port), ConsoleHandler)


def serve_console(
    *,
    config_path: str,
    entitlement_path: str,
    evidence_path: str,
    host: str = "127.0.0.1",
    port: int = 8765,
    public_key_b64: str | None = None,
) -> int:
    server = create_console_server(
        config_path=config_path,
        entitlement_path=entitlement_path,
        evidence_path=evidence_path,
        host=host,
        port=port,
        public_key_b64=public_key_b64,
    )
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
