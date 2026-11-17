#!/usr/bin/env python3
"""溟月 · 随机时刻投递：在配置的时间窗口里随机挑一刻，把一次性任务投递到用户会话。

同一套机制给三种主动行为用（各有一份配置 + 一个 shell 入口）：

    morning.json  → 08:00–10:30 随机一刻说早安      morning-schedule.sh
    share.json    → 12:00–14:00 / 21:00–23:00 各一次 share-schedule.sh

每天由定时任务在 00:0x 调用一次，先算好当天的时间点、建好一次性任务；到点由引擎投递。

    bash morning-schedule.sh                 # 规划今天（幂等：今天已规划就退出）
    bash morning-schedule.sh --dry-run       # 只算时间、打印请求体，不发请求
    bash morning-schedule.sh --in 180        # 测试：now + 180 秒投递（不写幂等标记）
    bash morning-schedule.sh --set-target ID # 设置目标会话（先问引擎这个会话在不在）
    bash morning-schedule.sh --force         # 忽略今天的幂等标记
    bash morning-schedule.sh --status        # 配置、今天的安排、最近日志

配置（缺了就写一份默认的）：

    {
      "targetSessionId": "session-…",
      "title": "溟月·早安",
      "prompt": "读 ~/mingyue/schedules/morning-hello.md，严格按里面的步骤执行。",
      "windows": [["08:00", "10:30"]],
      "skipChance": 0
    }

要点：
- target 必须是 {kind: "session", sessionId}；用 new 的话她会在新会话里自言自语。
- 一天每个窗口最多一条：幂等标记按「规划当天」记，全部建成功后才写。
- skipChance 按**每个窗口**独立掷一次（0.15 = 那个窗口有 15% 概率不安排）。
- 失败必须可见：原始响应和原因写进日志，退出码非 0。
"""

from __future__ import annotations

import argparse
import datetime as dt
import http.cookiejar
import json
import os
import random
import re
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

HOME_DIR = Path(os.environ.get("MINGYUE_HOME") or (Path.home() / "mingyue"))
WEB_LOG = Path.home() / ".dsh-app-remote" / "web.log"
MIN_LEAD_SECONDS = 120  # 窗口已过/引擎晚起时至少留 2 分钟，别建一个立刻到期的任务


class PingError(Exception):
    """可预期的失败：打印给人看，退出码 1。"""


# ---------------------------------------------------------------------------
# 配置、状态、日志


def now_ts() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Profile:
    """一份配置 + 它对应的状态文件与日志。"""

    def __init__(self, path: Path, stderr: bool = False) -> None:
        self.path = path
        stem = path.stem
        self.state_path = HOME_DIR / "tmp" / ("%s-state.json" % stem)
        self.log_path = HOME_DIR / "tmp" / ("%s.log" % stem)
        self.stderr = stderr

    def log(self, msg: str) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write("%s %s\n" % (now_ts(), msg))

    def say(self, msg: str) -> None:
        print(msg)
        self.log(msg)

    def load(self) -> dict:
        if not self.path.exists():
            defaults = default_config(self.path.stem)
            self.save(defaults)
            self.say("已创建默认配置 %s（targetSessionId 为空，先跑 --set-target <会话id>）" % self.path)
            return defaults
        try:
            cfg = json.loads(self.path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise PingError("配置不是合法 JSON（%s）：%s" % (self.path, exc))
        if not isinstance(cfg, dict):
            raise PingError("配置应是 JSON 对象：%s" % self.path)
        return cfg

    def save(self, cfg: dict) -> None:
        self.path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def state(self) -> dict:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def write_state(self, state: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def default_config(stem: str) -> dict:
    if stem == "share":
        return {
            "targetSessionId": "",
            "title": "溟月·分享",
            "prompt": "读 ~/mingyue/schedules/share-moment.md，严格按里面的步骤执行。",
            "windows": [["12:00", "14:00"], ["21:00", "23:00"]],
            "skipChance": 0.15,
        }
    return {
        "targetSessionId": "",
        "title": "溟月·早安",
        "prompt": "读 ~/mingyue/schedules/morning-hello.md，严格按里面的步骤执行。",
        "windows": [["08:00", "10:30"]],
        "skipChance": 0,
    }


def windows_of(cfg: dict) -> list:
    windows = cfg.get("windows")
    if windows is None and cfg.get("windowStart") and cfg.get("windowEnd"):
        windows = [[cfg["windowStart"], cfg["windowEnd"]]]  # 兼容旧的单窗口写法
    if not isinstance(windows, list) or not windows:
        raise PingError("配置里没有 windows（形如 [[\"08:00\",\"10:30\"]]）")
    return windows


# ---------------------------------------------------------------------------
# 引擎 RPC


class Engine:
    """只用 ~/.dsh-app-remote/web.log 里的启动行换 cookie；不打印 token。"""

    def __init__(self) -> None:
        port, token = self._launch()
        self.base = "http://127.0.0.1:%d" % port
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
        self._raw("%s/?token=%s" % (self.base, token), None, {})

    @staticmethod
    def _launch() -> tuple[int, str]:
        try:
            text = WEB_LOG.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise PingError("读不到引擎日志 %s：%s" % (WEB_LOG, exc))
        for raw in reversed(text.splitlines()):
            line = raw.strip()
            at = line.find("127.0.0.1:")
            if at < 0 or "/?token=" not in line:
                continue
            rest = line[at + len("127.0.0.1:"):]
            digits = ""
            for ch in rest:
                if not ch.isdigit():
                    break
                digits += ch
            token = line.rsplit("token=", 1)[1].strip()
            token = re.split(r"[^A-Za-z0-9_-]", token)[0] if token else ""
            if digits and token:
                return int(digits), token
        raise PingError("引擎日志里没有启动行（%s）——引擎没在跑？先开 App 连一次" % WEB_LOG)

    def _raw(self, url: str, data: bytes | None, headers: dict) -> bytes:
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with self.opener.open(req, timeout=20) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            body = exc.read()[:400].decode("utf-8", "replace")
            raise PingError("HTTP %s（%s）：%s" % (exc.code, url.rsplit("/api/", 1)[-1], body))
        except urllib.error.URLError as exc:
            raise PingError("连不上引擎（%s）：%s" % (url, exc.reason))

    def call(self, method: str, args: dict) -> object:
        rpc_id = "mingyue-ping-%s" % uuid.uuid4().hex[:12]
        envelope = {"type": "client-request", "rpcId": rpc_id, "method": method, "payload": {"args": args}}
        raw = self._raw(
            "%s/api/%s" % (self.base, method),
            json.dumps(envelope, ensure_ascii=False).encode("utf-8"),
            {"Content-Type": "application/json"},
        )
        try:
            doc = json.loads(raw.decode("utf-8"))
        except ValueError:
            raise PingError("%s 的响应不是 JSON：%s" % (method, raw[:400].decode("utf-8", "replace")))
        result = doc.get("result") or {}
        if result.get("ok") is not True:
            error = result.get("error") or {}
            raise PingError("%s 失败：%s: %s" % (method, error.get("code", "<no-code>"), error.get("message", "")))
        return result.get("value")


# ---------------------------------------------------------------------------
# 时间规划


def parse_hhmm(text: object, field: str) -> dt.time:
    try:
        return dt.datetime.strptime(str(text), "%H:%M").time()
    except ValueError:
        raise PingError("配置里的 %s 不是 HH:MM：%r" % (field, text))


def plan_in_window(span: tuple[str, str], now: float, lead: int) -> float | None:
    """在一个窗口里随机挑一刻；窗口已经整段过去就返回 None（跳过，不算失败）。"""
    start = parse_hhmm(span[0], "window start")
    end = parse_hhmm(span[1], "window end")
    today = dt.date.fromtimestamp(now)
    low = dt.datetime.combine(today, start)
    high = dt.datetime.combine(today, end)
    total = int((high - low).total_seconds())
    if total <= 0:
        raise PingError("窗口 %s–%s 为空（开始晚于结束）" % (start, end))
    chosen = low + dt.timedelta(seconds=random.randrange(total))
    if chosen.timestamp() <= now:
        # 引擎晚起（或白天手动补跑）：只从剩下的窗口里挑，不建过去时刻。
        low_epoch = max(now + lead, low.timestamp())
        high_epoch = high.timestamp()
        if high_epoch - low_epoch < 1:
            return None
        chosen = dt.datetime.fromtimestamp(random.randrange(int(low_epoch), int(high_epoch)))
    return chosen.timestamp()


def build_request(cfg: dict, target: str, at_iso: str) -> dict:
    title = cfg.get("title")
    prompt = cfg.get("prompt")
    if not isinstance(title, str) or not title.strip():
        raise PingError("配置里缺少 title")
    if not isinstance(prompt, str) or not prompt.strip():
        raise PingError("配置里缺少 prompt")
    return {
        "title": title,
        "prompt": prompt,
        "timing": {"kind": "at", "at": at_iso},
        "target": {"kind": "session", "sessionId": target},
    }


def iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def local(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# 子命令


def cmd_set_target(profile: Profile, session_id: str) -> int:
    if not session_id.startswith("session-"):
        raise PingError("会话 id 应以 session- 开头：%r" % session_id)
    value = Engine().call("session/list", {"_request": {}})
    items = value.get("items") if isinstance(value, dict) else None
    known = {item.get("sessionId") for item in (items or []) if isinstance(item, dict)}
    if session_id not in known:
        raise PingError("引擎里没有这个会话：%s（现有 %d 个会话，用 App 会话详情里的 id）" % (session_id, len(known)))
    cfg = profile.load()
    cfg["targetSessionId"] = session_id
    profile.save(cfg)
    profile.say("已设置目标会话：%s（%s）" % (session_id, profile.path))
    return 0


def cmd_status(profile: Profile) -> int:
    cfg = profile.load()
    print("配置 %s" % profile.path)
    print("  targetSessionId %s" % cfg.get("targetSessionId", ""))
    print("  title           %s" % cfg.get("title", ""))
    print("  prompt          %s" % cfg.get("prompt", ""))
    print("  skipChance      %s" % cfg.get("skipChance", 0))
    for span in windows_of(cfg):
        print("  window          %s–%s" % (span[0], span[1]))
    state = profile.state()
    print("状态 %s" % profile.state_path)
    tasks = state.get("tasks")
    if isinstance(tasks, list) and tasks:
        for task in tasks:
            print("  %-13s %s @ %s" % (task.get("window", ""), task.get("taskId", ""), task.get("local", "")))
    elif state.get("taskId"):
        print("  %-13s %s @ %s（旧格式）" % ("", state.get("taskId"), state.get("scheduledAt", "")))
    else:
        print("  （今天还没有安排记录）")
    if profile.log_path.exists():
        lines = profile.log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-5:]
        print("日志 %s（最后 %d 行）" % (profile.log_path, len(lines)))
        for line in lines:
            print("  %s" % line)
    return 0


def cmd_plan(profile: Profile, args: argparse.Namespace) -> int:
    cfg = profile.load()
    target = str(cfg.get("targetSessionId") or "")
    if not target:
        raise PingError("配置里没有 targetSessionId：先跑 --set-target <会话id>")

    now = dt.datetime.now().timestamp()
    today = dt.date.fromtimestamp(now).isoformat()

    if args.in_seconds is not None:
        items = [(("now+%ds" % args.in_seconds), now + args.in_seconds)]
        mode = "测试（now+%d 秒）" % args.in_seconds
        force = True
    else:
        state = profile.state()
        if state.get("date") == today and not args.force:
            planned = state.get("tasks") or []
            detail = ", ".join("%s @ %s" % (t.get("window", "?"), t.get("local", "?")) for t in planned) or state.get("taskId", "?")
            profile.say("今天（%s）已经安排过：%s，跳过" % (today, detail))
            return 0
        skip = float(cfg.get("skipChance") or 0)
        items = []
        for span in windows_of(cfg):
            label = "%s–%s" % (span[0], span[1])
            if skip > 0 and random.random() < skip:
                profile.say("窗口 %s 按 skipChance=%.2f 跳过" % (label, skip))
                continue
            at_epoch = plan_in_window((span[0], span[1]), now, MIN_LEAD_SECONDS)
            if at_epoch is None:
                profile.say("窗口 %s 已经过去，今天跳过这个窗口" % label)
                continue
            items.append((label, at_epoch))
        mode = "计划"
        force = False
        if not items:
            profile.say("今天（%s）没有要安排的窗口（窗口已过或按 skipChance 跳过）" % today)
            return 0

    requests = []
    for label, at_epoch in items:
        at_iso = iso(at_epoch)
        print("%s：%s（%s）" % (mode, local(at_epoch), at_iso))
        print("目标会话：%s" % target)
        requests.append((label, at_epoch, at_iso, build_request(cfg, target, at_iso)))

    if args.dry_run:
        for _label, _epoch, _iso, request in requests:
            print("请求体：")
            print(
                json.dumps(
                    {
                        "type": "client-request",
                        "rpcId": "<uuid>",
                        "method": "schedule/create",
                        "payload": {"args": {"request": request}},
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        profile.log("dry-run：%s" % ", ".join("%s @ %s" % (label, iso(epoch)) for label, epoch, _i, _r in requests))
        return 0

    engine = Engine()
    planned = []
    failed = 0
    for label, at_epoch, at_iso, request in requests:
        try:
            value = engine.call("schedule/create", {"request": request})
            if not isinstance(value, dict) or not value.get("id"):
                raise PingError("schedule/create 返回了不认识的形状：%r" % (value,))
        except PingError as exc:
            failed += 1
            profile.say("窗口 %s 失败：%s" % (label, exc))
            continue
        planned.append(
            {
                "window": label,
                "taskId": value["id"],
                "scheduledAt": value.get("scheduledAt", at_iso),
                "local": local(at_epoch),
            }
        )
        profile.say("已安排：窗口 %s → task %s，计划 %s（%s）" % (label, value["id"], local(at_epoch), value.get("scheduledAt", at_iso)))

    if planned and not force:
        profile.write_state(
            {
                "date": today,
                "tasks": planned,
                "plannedAt": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            }
        )
    if failed:
        profile.say("有 %d 个窗口失败（见上），今天成功 %d 个" % (failed, len(planned)))
        return 1
    return 0


def parse_args(profile_default: Path, argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="溟月 · 随机时刻投递")
    parser.add_argument("--config", default=str(profile_default), help="配置文件路径（默认 %s）" % profile_default)
    parser.add_argument("--dry-run", action="store_true", help="只算时间、打印请求体，不发请求")
    parser.add_argument("--in", dest="in_seconds", type=int, metavar="SECONDS", help="测试：now+N 秒投递（不写幂等标记）")
    parser.add_argument("--set-target", metavar="SESSION_ID", help="设置目标会话 id")
    parser.add_argument("--force", action="store_true", help="忽略今天的幂等标记")
    parser.add_argument("--status", action="store_true", help="打印配置、今天的安排和日志尾部")
    args = parser.parse_args(argv)
    if args.in_seconds is not None and args.in_seconds <= 0:
        parser.error("--in 需要正整数秒")
    return args


def main(argv: list[str], default_config_path: Path | None = None) -> int:
    default_path = default_config_path or (HOME_DIR / "morning.json")
    args = parse_args(default_path, argv)
    profile = Profile(Path(args.config).expanduser())
    try:
        if args.set_target:
            return cmd_set_target(profile, args.set_target)
        if args.status:
            return cmd_status(profile)
        return cmd_plan(profile, args)
    except PingError as exc:
        profile.say("ERROR: %s" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
