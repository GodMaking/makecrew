"""Dependency-free local web demo."""

from __future__ import annotations

import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .router import route_task


def render_result(task: str, project: str = "") -> str:
    if not task:
        return ""
    result = route_task(task, project)
    cards = " ".join(
        f"<div class='card'><b>{html.escape(label)}</b><br>{html.escape(value)}</div>"
        for label, value in (("路由", result["route"]), ("负责人", result["lead"]), ("领域", "、".join(result["domains"])), ("轮次预算", str(result["budget"]["max_rounds"])))
    )
    assignments = "".join(f"<li>{html.escape(item['role'])}：{html.escape(item['objective'])}；交付 {html.escape(item['output'])}</li>" for item in result["parallel_tasks"]) or "<li>直接由负责人处理，无需组建协作组。</li>"
    gates = "".join(f"<li>{html.escape(gate)}</li>" for gate in result["acceptance_gates"])
    return f"<div class='grid'>{cards}</div><h2>并行任务</h2><ul>{assignments}</ul><h2>验收门禁</h2><ul>{gates}</ul><h2>下一步</h2><p>{html.escape(result['next_action'])}</p><details><summary>结构化结果</summary><pre>{html.escape(json.dumps(result, ensure_ascii=False, indent=2))}</pre></details>"


PAGE = """<!doctype html><html lang='zh-CN'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>AI Company OS</title><style>body{font-family:system-ui;max-width:900px;margin:30px auto;padding:0 18px;background:#f5f7fb;color:#172033}main{background:#fff;padding:26px;border:1px solid #dfe5ef;border-radius:10px}textarea,input{box-sizing:border-box;width:100%;padding:11px;margin:7px 0 12px;border:1px solid #bbc6d8;border-radius:6px;font:inherit}textarea{min-height:105px}button{padding:11px 18px;background:#1769e0;color:#fff;border:0;border-radius:6px;font-weight:600}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin-top:20px}.card{padding:12px;background:#f0f4fa;border:1px solid #dce4f0;border-radius:6px}pre{background:#111827;color:#e7eef9;padding:14px;overflow:auto;white-space:pre-wrap}</style><main><h1>AI Company OS</h1><p>输入任务，查看路由、协作组、验收门禁和 Token 预算。</p><form><label>任务描述</label><textarea name='task' placeholder='例如：开发网站并准备上线，同时研究用户并写宣传文案'>{task}</textarea><label>项目名（可选）</label><input name='project' value='{project}'><button>生成协作计划</button></form>{result}</main></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        query = parse_qs(urlparse(self.path).query)
        task = query.get("task", [""])[0]
        project = query.get("project", [""])[0]
        body = PAGE.replace("{task}", html.escape(task)).replace("{project}", html.escape(project)).replace("{result}", render_result(task, project)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve(host: str = "127.0.0.1", port: int = 8787) -> None:
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"AI Company OS demo: http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
