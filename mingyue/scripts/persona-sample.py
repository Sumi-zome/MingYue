#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""溟月 · 人设盲测采样器（在主机 Termux 上跑，只用标准库）。

为什么要它：交接包的迭代协议要求「固定测试集 + 每句 3 条样本 + 用户盲评」，
而「在 App 里逐句聊」既不可复现也拿不到原始文本。这个脚本直接走主机上正在运行的
`dsh web` 的 HTTP RPC，用和 App 相同的会话/人设（工作区 ~/mingyue，AGENTS.md
自动注入），把回复原样抓下来。

不碰记忆库、不碰定时任务；只读启动令牌换 cookie，不上网。

用法：
  python3 persona-sample.py list
  python3 persona-sample.py dump <sessionId> [--chars 600] [--raw]
  python3 persona-sample.py say "今天好累" [--session session-...] [--image PATH]
  python3 persona-sample.py suite [--runs 3] [--out lab/persona-samples.json]

退出码：0 成功；1 引擎不可用 / RPC 失败 / 等待超时；2 用法。
"""

import argparse
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

HOME = Path(os.environ.get("MINGYUE_USER_HOME") or Path.home())
WEB_LOG = HOME / ".dsh-app-remote" / "web.log"
WORKSPACE = HOME / "mingyue"
URL_RE = re.compile(r"http://127\.0\.0\.1:(\d+)/\?token=([A-Za-z0-9_-]+)")

# 固定测试集（交接包 §迭代协议 1）；顺序有意义：「我胡说的」要靠前两句做参照。
DEFAULT_SUITE = [
    ("T1", "今天好累"),
    ("T2", "你看这个 https://example.com/some-shared-link"),
    ("T3", "你还记得我上次说的那个事吗"),
    ("T4", "我胡说的"),
    ("T5", "嗯"),
]


def die(msg, code=1):
    print("错误：%s" % msg, file=sys.stderr)
    return code


class Engine:
    """一台正在运行的 dsh web：登录令牌 → cookie → /api/<method> RPC。"""

    def __init__(self, log_path=WEB_LOG):
        if not log_path.exists():
            raise RuntimeError("找不到 %s（引擎没在跑？先开 App 连一次主机）" % log_path)
        found = URL_RE.findall(log_path.read_text(encoding="utf-8", errors="replace"))
        if not found:
            raise RuntimeError("web.log 里没有启动行（引擎没在跑？）")
        self.port, token = found[-1]
        self.base = "http://127.0.0.1:%s" % self.port
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        with self.opener.open(self.base + "/?token=" + token, timeout=30) as resp:
            resp.read()

    def rpc(self, method, args):
        rpc_id = str(uuid.uuid4())
        body = json.dumps({"type": "client-request", "rpcId": rpc_id,
                           "method": method, "payload": {"args": args}}).encode("utf-8")
        req = urllib.request.Request(self.base + "/api/" + method, data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(req, timeout=180) as resp:
                status, text = resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            raise RuntimeError("%s: HTTP %s %s" % (method, exc.code, exc.read()[:300]))
        if status != 200:
            raise RuntimeError("%s: HTTP %s" % (method, status))
        decoded = json.loads(text)
        if decoded.get("type") != "server-response":
            raise RuntimeError("%s: 不是 server-response" % method)
        result = decoded.get("result") or {}
        if not result.get("ok"):
            err = result.get("error") or {}
            raise RuntimeError("%s: %s %s" % (method, err.get("code"), err.get("message")))
        return result.get("value")

    # -- 会话读取 ---------------------------------------------------------

    def sessions(self):
        return (self.rpc("session/list", {"_request": {}}) or {}).get("items") or []

    def projections(self, session_id):
        return self.rpc("session/projections", {"request": {"sessionId": session_id}}) or {}

    def page(self, session_id, through_seq, max_messages=200):
        return self.rpc("session/page", {"request": {
            "address": {"kind": "session", "sessionId": session_id},
            "throughSeq": through_seq,
            "maxMessages": max_messages,
        }}) or {}

    def events(self, session_id, max_messages=200):
        seq = int(self.projections(session_id).get("asOfSeq", -1))
        page = self.page(session_id, seq, max_messages)
        return [rec.get("event") or rec for rec in page.get("records") or []]

    # -- 会话写入 ---------------------------------------------------------

    def create(self, cwd=None):
        value = self.rpc("session/create", {"request": {"cwd": str(cwd or WORKSPACE)}}) or {}
        return value.get("sessionId", "")

    def prompt(self, session_id, text, images=()):
        content = [{"type": "text", "text": text}] if text else []
        for path in images:
            data = Path(path).read_bytes()
            suffix = Path(path).suffix.lower()
            media = {".png": "image/png", ".webp": "image/webp",
                     ".gif": "image/gif"}.get(suffix, "image/jpeg")
            import base64
            content.append({"type": "image", "mediaType": media,
                            "data": base64.b64encode(data).decode("ascii"),
                            "name": Path(path).name})
        self.rpc("session/prompt", {"request": {
            "requestId": str(uuid.uuid4()),
            "sessionId": session_id,
            "mode": "queue",
            "content": content,
            "clientTimeZone": "Asia/Shanghai",
        }})

    def wait_reply(self, session_id, before_assistant, timeout=240, poll=2.0):
        """等这一轮跑完，返回 (新增 assistant 文本, 行摘要)。"""
        deadline = time.time() + timeout
        last, started = None, False
        while time.time() < deadline:
            row = next((s for s in self.sessions() if s.get("sessionId") == session_id), None)
            if row and row.get("running"):
                started = True
            last = row
            texts = assistant_texts(self.events(session_id))
            if len(texts) > before_assistant and not (row and row.get("running")):
                return texts[before_assistant:], row
            time.sleep(poll)
        return None, last


def part_text(part):
    kind = part.get("type")
    if kind == "text":
        return part.get("text", "")
    if kind == "image":
        return "[图片]"
    if kind == "toolCall":
        return "[工具:%s]" % part.get("name")
    return ""


def message_text(message):
    return "".join(part_text(p) for p in (message.get("content") or []) if isinstance(p, dict))


def assistant_texts(events):
    out = []
    for ev in events:
        if ev.get("type") != "assistant/message":
            continue
        msg = (ev.get("data") or {}).get("message") or {}
        text = message_text(msg).strip()
        if text:
            out.append(text)
    return out


def user_texts(events):
    out = []
    for ev in events:
        if ev.get("type") != "user/message":
            continue
        msg = (ev.get("data") or {}).get("message") or {}
        out.append(message_text(msg).strip())
    return out


# -- 命令 -----------------------------------------------------------------

def cmd_list(engine, args):
    for s in engine.sessions():
        print("%s  running=%-5s  %s" % (s.get("sessionId"), str(s.get("running")),
                                        (s.get("title") or "")[:40]))
    return 0


def cmd_dump(engine, args):
    events = engine.events(args.session, max_messages=500)
    if args.raw:
        print(json.dumps(events[:2], ensure_ascii=False, indent=2)[:4000])
        return 0
    for ev in events:
        kind = ev.get("type")
        if kind not in ("user/message", "assistant/message"):
            continue
        msg = (ev.get("data") or {}).get("message") or {}
        text = message_text(msg)
        if text:
            print("<%s> %s" % (msg.get("role"), text[:args.chars]))
    return 0


def cmd_say(engine, args):
    sid = args.session or engine.create()
    before = len(assistant_texts(engine.events(sid)))
    engine.prompt(sid, args.text or "", images=args.image or [])
    texts, row = engine.wait_reply(sid, before)
    if texts is None:
        return die("等待回复超时（session=%s running=%s）" % (sid, (row or {}).get("running")), 1)
    print("session=%s" % sid)
    for text in texts:
        print(text)
    return 0


def cmd_suite(engine, args):
    suite = DEFAULT_SUITE
    if args.suite:
        suite = [(t["id"], t["text"]) for t in json.loads(Path(args.suite).read_text(encoding="utf-8"))]
    runs, records = [], []
    for run in range(1, args.runs + 1):
        sid = engine.create()
        print("[run %d] session=%s" % (run, sid), file=sys.stderr)
        for case_id, text in suite:
            before = len(assistant_texts(engine.events(sid)))
            engine.prompt(sid, text)
            replies, row = engine.wait_reply(sid, before)
            if replies is None:
                records.append({"run": run, "case": case_id, "input": text,
                                "session": sid, "error": "timeout"})
                print("[run %d/%s] 超时" % (run, case_id), file=sys.stderr)
                continue
            for i, reply in enumerate(replies, 1):
                records.append({"run": run, "case": case_id, "input": text,
                                "session": sid, "sample": i, "reply": reply})
            print("[run %d/%s] %s" % (run, case_id, " / ".join(replies)), file=sys.stderr)
            runs.append((run, case_id, replies))
    payload = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "runs": args.runs,
               "suite": [{"id": i, "text": t} for i, t in suite], "records": records}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[saved] %s（%d 条回复）" % (out, len(records)), file=sys.stderr)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="persona-sample.py", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")

    dump = sub.add_parser("dump")
    dump.add_argument("session")
    dump.add_argument("--chars", type=int, default=600)
    dump.add_argument("--raw", action="store_true")

    say = sub.add_parser("say")
    say.add_argument("text", nargs="?")
    say.add_argument("--session")
    say.add_argument("--image", action="append")

    suite = sub.add_parser("suite")
    suite.add_argument("--runs", type=int, default=3)
    suite.add_argument("--suite")
    suite.add_argument("--out", default=str(WORKSPACE / "lab" / "persona-samples.json"))

    args = parser.parse_args(argv)
    try:
        engine = Engine()
    except Exception as exc:  # noqa: BLE001  （引擎没起来时给一句话，不甩栈）
        return die(str(exc), 1)
    try:
        handler = {"list": cmd_list, "dump": cmd_dump, "say": cmd_say, "suite": cmd_suite}[args.cmd]
        return handler(engine, args)
    except RuntimeError as exc:
        return die(str(exc), 1)


if __name__ == "__main__":
    sys.exit(main())
