from __future__ import annotations

import json
import sys
import traceback
from typing import Any, Callable

from thinktofinish_company.contracts import validate_task_contract
from thinktofinish_company.metrics import record_task_metric, summary as metrics_summary
from thinktofinish_company.policy import check_policy
from thinktofinish_company.release import check_release_evidence
from thinktofinish_company.status import company_status
from thinktofinish_company.traceability import (
    find_path,
    query_node,
    record_edge,
    record_node,
    requirement_coverage,
)

SERVER_INFO = {
    "name": "thinktofinish-company",
    "version": "0.1.0",
    "description": "Company governance and delivery evidence for Hermes Agent software projects.",
}
SUPPORTED_VERSIONS = [
    "2026-07-28",
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
]


def _schema(properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties or {},
        "required": required or [],
        "additionalProperties": False,
    }


def _obj(description: str = "JSON object") -> dict[str, Any]:
    return {"type": "object", "description": description, "additionalProperties": True}


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "ttf_company_status",
        "description": "Return the active ThinkToFinish Company Layer version and operating principles.",
        "inputSchema": _schema(),
    },
    {
        "name": "ttf_policy_check",
        "description": "Classify a proposed company action as autonomous, human approval, or forbidden.",
        "inputSchema": _schema(
            {
                "action": {"type": "string"},
                "risk": {"type": "string", "enum": ["low", "medium", "high", "critical"], "default": "medium"},
                "context": {"type": "string", "default": ""},
            },
            ["action"],
        ),
    },
    {
        "name": "ttf_validate_task_contract",
        "description": "Validate a Company Task Contract before a Hermes Kanban task is executed.",
        "inputSchema": _schema({"contract": _obj("Company Task Contract")}, ["contract"]),
    },
    {
        "name": "ttf_trace_node",
        "description": "Record or update a traceability node: requirement, ADR, task, commit, PR, test, or release.",
        "inputSchema": _schema(
            {
                "project": {"type": "string"},
                "node_type": {"type": "string"},
                "node_id": {"type": "string"},
                "title": {"type": "string", "default": ""},
                "metadata": _obj("Optional metadata without secrets"),
            },
            ["project", "node_type", "node_id"],
        ),
    },
    {
        "name": "ttf_trace_edge",
        "description": "Record a directed traceability link between two delivery artifacts.",
        "inputSchema": _schema(
            {
                "project": {"type": "string"},
                "source_type": {"type": "string"},
                "source_id": {"type": "string"},
                "target_type": {"type": "string"},
                "target_id": {"type": "string"},
                "relation": {"type": "string"},
                "metadata": _obj("Optional metadata without secrets"),
            },
            ["project", "source_type", "source_id", "target_type", "target_id", "relation"],
        ),
    },
    {
        "name": "ttf_trace_query",
        "description": "Show incoming and outgoing traceability links for one artifact.",
        "inputSchema": _schema(
            {"project": {"type": "string"}, "node_type": {"type": "string"}, "node_id": {"type": "string"}},
            ["project", "node_type", "node_id"],
        ),
    },
    {
        "name": "ttf_trace_path",
        "description": "Find whether a traceability path exists from one artifact to a target artifact type.",
        "inputSchema": _schema(
            {
                "project": {"type": "string"},
                "source_type": {"type": "string"},
                "source_id": {"type": "string"},
                "target_type": {"type": "string"},
            },
            ["project", "source_type", "source_id", "target_type"],
        ),
    },
    {
        "name": "ttf_requirement_coverage",
        "description": "Measure requirement coverage across task, PR, test, and release traceability paths.",
        "inputSchema": _schema({"project": {"type": "string"}}, ["project"]),
    },
    {
        "name": "ttf_release_gate",
        "description": "Evaluate release evidence against quality, security, traceability, and human-approval policy.",
        "inputSchema": _schema({"evidence": _obj("Release evidence object")}, ["evidence"]),
    },
    {
        "name": "ttf_metrics_record",
        "description": "Record terminal task metrics for company learning and autonomy measurement.",
        "inputSchema": _schema(
            {
                "project": {"type": "string"},
                "task_id": {"type": "string"},
                "status": {"type": "string"},
                "cycle_seconds": {"type": "number", "default": 0},
                "retries": {"type": "integer", "default": 0},
                "human_interventions": {"type": "integer", "default": 0},
                "cost_usd": {"type": "number", "default": 0},
                "first_pass": {"type": "boolean", "default": false},
                "autonomous": {"type": "boolean", "default": false},
                "metadata": _obj("Optional metric metadata"),
            },
            ["project", "task_id", "status"],
        ),
    },
    {
        "name": "ttf_metrics_summary",
        "description": "Summarize cycle time, retries, interventions, cost, first-pass rate, and autonomous completion rate.",
        "inputSchema": _schema({"project": {"type": "string"}}, ["project"]),
    },
]


def _call_status(_: dict[str, Any]) -> Any:
    return company_status()


def _call_policy(a: dict[str, Any]) -> Any:
    return check_policy(a["action"], a.get("risk", "medium"), a.get("context", ""))


def _call_contract(a: dict[str, Any]) -> Any:
    return validate_task_contract(a["contract"])


def _call_trace_node(a: dict[str, Any]) -> Any:
    return record_node(a["project"], a["node_type"], a["node_id"], a.get("title", ""), a.get("metadata"))


def _call_trace_edge(a: dict[str, Any]) -> Any:
    return record_edge(
        a["project"], a["source_type"], a["source_id"], a["target_type"], a["target_id"], a["relation"], a.get("metadata")
    )


def _call_trace_query(a: dict[str, Any]) -> Any:
    return query_node(a["project"], a["node_type"], a["node_id"])


def _call_trace_path(a: dict[str, Any]) -> Any:
    return find_path(a["project"], a["source_type"], a["source_id"], a["target_type"])


def _call_coverage(a: dict[str, Any]) -> Any:
    return requirement_coverage(a["project"])


def _call_release(a: dict[str, Any]) -> Any:
    return check_release_evidence(a["evidence"])


def _call_metrics_record(a: dict[str, Any]) -> Any:
    return record_task_metric(
        a["project"],
        a["task_id"],
        a["status"],
        a.get("cycle_seconds", 0),
        a.get("retries", 0),
        a.get("human_interventions", 0),
        a.get("cost_usd", 0),
        a.get("first_pass", False),
        a.get("autonomous", False),
        a.get("metadata"),
    )


def _call_metrics_summary(a: dict[str, Any]) -> Any:
    return metrics_summary(a["project"])


TOOL_HANDLERS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "ttf_company_status": _call_status,
    "ttf_policy_check": _call_policy,
    "ttf_validate_task_contract": _call_contract,
    "ttf_trace_node": _call_trace_node,
    "ttf_trace_edge": _call_trace_edge,
    "ttf_trace_query": _call_trace_query,
    "ttf_trace_path": _call_trace_path,
    "ttf_requirement_coverage": _call_coverage,
    "ttf_release_gate": _call_release,
    "ttf_metrics_record": _call_metrics_record,
    "ttf_metrics_summary": _call_metrics_summary,
}


def _server_meta() -> dict[str, Any]:
    return {"io.modelcontextprotocol/serverInfo": SERVER_INFO}


def _result(payload: dict[str, Any], modern: bool = False) -> dict[str, Any]:
    if modern:
        payload = dict(payload)
        payload.setdefault("resultType", "complete")
        payload.setdefault("_meta", _server_meta())
    return payload


def handle_message(message: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return {"jsonrpc": "2.0", "id": message.get("id") if isinstance(message, dict) else None, "error": {"code": -32600, "message": "Invalid Request"}}

    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}
    modern = False
    if isinstance(params, dict):
        meta = params.get("_meta") or {}
        modern = isinstance(meta, dict) and meta.get("io.modelcontextprotocol/protocolVersion") == "2026-07-28"

    # Notifications have no id and must not receive a response.
    if request_id is None:
        return None

    try:
        if method == "server/discover":
            payload = {
                "supportedVersions": SUPPORTED_VERSIONS,
                "capabilities": {"tools": {"listChanged": False}},
                "instructions": "Use ThinkToFinish tools for policy, contracts, traceability, release evidence, and delivery metrics. Hermes remains responsible for Kanban execution.",
            }
            return {"jsonrpc": "2.0", "id": request_id, "result": _result(payload, modern=True)}

        if method == "initialize":
            requested = params.get("protocolVersion") if isinstance(params, dict) else None
            protocol = requested if requested in SUPPORTED_VERSIONS else "2025-11-25"
            payload = {
                "protocolVersion": protocol,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
                "instructions": "Company governance layer for Hermes software delivery.",
            }
            return {"jsonrpc": "2.0", "id": request_id, "result": payload}

        if method == "ping":
            return {"jsonrpc": "2.0", "id": request_id, "result": {}}

        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": _result({"tools": TOOL_SPECS}, modern=modern)}

        if method == "tools/call":
            if not isinstance(params, dict):
                raise ValueError("params must be an object")
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if name not in TOOL_HANDLERS:
                return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Unknown tool: {name}"}}
            if not isinstance(arguments, dict):
                raise ValueError("tool arguments must be an object")
            output = TOOL_HANDLERS[name](arguments)
            text = json.dumps(output, ensure_ascii=False, sort_keys=True)
            payload = {
                "content": [{"type": "text", "text": text}],
                "structuredContent": output if isinstance(output, dict) else {"value": output},
                "isError": False,
            }
            return {"jsonrpc": "2.0", "id": request_id, "result": _result(payload, modern=modern)}

        if method == "resources/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": _result({"resources": []}, modern=modern)}

        if method == "prompts/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": _result({"prompts": []}, modern=modern)}

        if method == "logging/setLevel":
            return {"jsonrpc": "2.0", "id": request_id, "result": {}}

        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}
    except KeyError as exc:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": f"Missing required argument: {exc.args[0]}"}}
    except (TypeError, ValueError) as exc:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32602, "message": str(exc)}}
    except Exception as exc:  # fail closed at the tool boundary, never corrupt stdout
        traceback.print_exc(file=sys.stderr)
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": f"Internal error: {type(exc).__name__}"}}


def main() -> None:
    # MCP stdio uses one JSON-RPC message per line. Never print non-protocol data to stdout.
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            response = handle_message(message)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
