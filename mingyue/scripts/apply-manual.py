#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 persona.md + rules.md 拼进 <home>/AGENTS.md 的**手工区**（CORE marker 之外）。

为什么需要它：DSH 只自动注入工作区的 AGENTS.md；`mem.py render` 只替换 CORE marker 之间，
所以人设与规则要落在 marker 之外的手工区，且 render 逐字节保留。
方案 A：改完 persona.md / rules.md 后重跑本脚本（幂等），不要手改 AGENTS.md 手工区。

用法：
  python3 apply-manual.py [--home DIR] [--check]
退出码：0 成功/已一致；1 --check 发现不一致；2 用法；3 校验失败（未改动）；4 IO/状态。
"""

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mem  # noqa: E402  （复用 marker 常量、home 解析与原子写）


def build_manual(agents_text, persona_text, rules_text):
    """保留 CORE 区（含 markers）不动，重写 marker 之外的手工区。"""
    end = agents_text.find(mem.MARK_END)
    if end < 0:
        raise mem.MemError("AGENTS.md 里找不到 %s 标记；未改动原文件（先跑 mem.py render）"
                           % mem.MARK_END, mem.EXIT_STATE)
    line_start = agents_text.rfind("\n", 0, end) + 1
    if agents_text[line_start:end].strip():
        raise mem.MemError("END 标记必须单独占一行；未改动原文件", mem.EXIT_STATE)
    line_end = agents_text.find("\n", end)
    head = agents_text if line_end < 0 else agents_text[:line_end + 1]
    if not head.endswith("\n\n"):
        head = head.rstrip("\n") + "\n\n"
    manual = (mem.MANUAL_HINT + "\n\n"
              + persona_text.strip("\n") + "\n\n"
              + rules_text.strip("\n") + "\n")
    return head + manual


def main(argv=None):
    mem._utf8_stdio()
    parser = argparse.ArgumentParser(
        prog="apply-manual.py",
        description="把 persona.md + rules.md 拼进 AGENTS.md 手工区（CORE 区不动）")
    parser.add_argument("--home", help="家目录（默认 $MINGYUE_HOME 或 ~/mingyue）")
    parser.add_argument("--check", action="store_true", help="只比对不落盘")
    args = parser.parse_args(argv)
    try:
        home = mem.home_of(args)
        agents = mem.agents_path(home)
        persona = home / "persona.md"
        rules = home / "rules.md"
        for path in (agents, persona, rules):
            if not path.exists():
                raise mem.MemError("找不到 %s（先部署该文件）" % path, mem.EXIT_STATE)
        original = agents.read_text(encoding="utf-8")
        new = build_manual(original, persona.read_text(encoding="utf-8"),
                           rules.read_text(encoding="utf-8"))
        if args.check:
            if new == original:
                print("[ OK ] %s 手工区与 persona.md / rules.md 一致" % agents)
                return mem.EXIT_OK
            print("[DIFF] %s 手工区需要更新：python3 scripts/apply-manual.py" % agents)
            return 1
        if new == original:
            print("[NOOP] %s 手工区已一致" % agents)
            return mem.EXIT_OK
        mem.atomic_write(agents, new)
        print("[MANUAL] %s（persona.md + rules.md → 手工区；CORE 区未动）" % agents)
        return mem.EXIT_OK
    except mem.MemError as exc:
        print("错误：%s" % exc, file=sys.stderr)
        return exc.code
    except OSError as exc:
        print("错误：读写失败：%s" % exc, file=sys.stderr)
        return mem.EXIT_STATE


if __name__ == "__main__":
    sys.exit(main())
