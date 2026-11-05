#!/usr/bin/env python3
"""DK 决策验证层 —— TypeSafe System One（类 jev）硅基流动 Serverless 客户端。

协议来源：typesafe-sdk 0.7.1 源码（_core/endpoints.py + _schemas/models.py）。
  POST {base}/v1/systemone
    body: {"state": <str|obj>, "model": "<id>", "questions": {name: question}}
    question: {"type": "noul",   "instructions", "criteria": {"true","false"}}
            | {"type": "choice", "instructions", "criteria": {label: desc}}
            | {"type": "score",  "instructions", "criteria": [level0, level1, ...]}
  resp: {"model", "answers": {name: answer}, "usage": {"input_tokens","output_tokens"}}
    answer: {"type":"noul","noul":float}        # P(yes)∈[0,1]
          | {"type":"choice","choice":str,"confidence":float,"probabilities":{label:p}}
          | {"type":"score","score":float,"confidence":float,"legend","probabilities"}

凭据从 ~/.openviking/ov.conf 的 embedding.dense.api_key 读取（与 rerank-router 同源），
不出现在命令行/源码里。

用法：
  jev-judge.py --list-models
  echo '{"state":"...","questions":{...}}' | jev-judge.py [--model SemIf]
  jev-judge.py --model kev-4b --input req.json --output out.json
未指定 --model 时用 DEFAULT_MODEL。questions 缺省 type=choice 不允许，必须显式。
"""
import argparse
import datetime
import http.client
import json
import os
import sys
from urllib.error import HTTPError

API_HOST = "api.hal-x.ai"
DEFAULT_MODEL = "THX-01"


def _request(method: str, path: str, body: dict | None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    conn = http.client.HTTPSConnection(API_HOST, timeout=60)  # 仅 https，无 scheme 注入面
    try:
        conn.request(
            method,
            path,
            body=data,
            headers={"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        payload = resp.read().decode("utf-8", "replace")
        if resp.status >= 400:
            sys.stderr.write(f"HTTP {resp.status} {path}: {payload[:500]}\n")
            raise SystemExit(2)
        return json.loads(payload)
    except HTTPError:
        raise SystemExit(2) from None
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="TypeSafe System One judge (SiliconFlow serverless)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--input", help="请求 JSON 文件；缺省读 stdin")
    ap.add_argument("--output", help="响应写入文件；缺省打印 stdout")
    ap.add_argument("--list-models", action="store_true", help="GET /v1/models 列出可用模型名")
    args = ap.parse_args()

    if args.list_models:
        out = _request("GET", "/v1/models", None)
        models = out.get("data", out.get("models", out))
        print(json.dumps(models, ensure_ascii=False, indent=2))
        return

    if args.input:
        with open(args.input, encoding="utf-8") as fh:
            raw = fh.read()
    else:
        raw = sys.stdin.read()
    body = json.loads(raw)
    body.setdefault("model", args.model)
    missing = {"state", "questions"} - body.keys()
    if missing:
        sys.stderr.write(f"missing keys: {sorted(missing)}\n")
        raise SystemExit(2)
    resp = _request("POST", "/v1/systemone", body)
    text = json.dumps(resp, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
