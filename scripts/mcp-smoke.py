#!/usr/bin/env python3
"""Zero-dependency smoke test for the ThinkToFinish MCP stdio server."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def send(proc: subprocess.Popen[str], message: dict) -> dict | None:
    assert proc.stdin is not None
    assert proc.stdout is not None
    proc.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
    proc.stdin.flush()
    if "id" not in message:
        return None
    raw = proc.stdout.readline()
    if not raw:
        stderr = proc.stderr.read() if proc.stderr else ""
        raise RuntimeError(f"MCP server exited before responding: {stderr}")
    result = json.loads(raw)
    if "error" in result:
        raise RuntimeError(f"MCP error: {result['error']}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default=str(Path(__file__).resolve().parents[1] / "server.py"))
    args = parser.parse_args()

    server = Path(args.server).resolve()
    proc = subprocess.Popen(
        [sys.executable, str(server)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        cwd=str(server.parent),
    )
    try:
        legacy = send(proc, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "smoke", "version": "1"}},
        })
        assert legacy and legacy["result"]["serverInfo"]["name"] == "thinktofinish-company"
        send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

        tools = send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        names = {tool["name"] for tool in tools["result"]["tools"]}
        required = {"ttf_company_status", "ttf_policy_check", "ttf_release_gate", "ttf_metrics_summary"}
        assert required.issubset(names)

        policy = send(proc, {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "ttf_policy_check", "arguments": {"action": "production_deployment", "risk": "medium"}},
        })
        assert policy["result"]["structuredContent"]["decision"] == "human_approval"

        modern = send(proc, {
            "jsonrpc": "2.0", "id": 4, "method": "server/discover",
            "params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}},
        })
        assert "2026-07-28" in modern["result"]["supportedVersions"]
        assert modern["result"]["resultType"] == "complete"
        print(f"MCP_SMOKE_OK {len(names)}")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())
