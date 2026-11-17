#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""溟月 · mem.py 自查（PC 和 Termux 手机都能跑，只用标准库）。

    python3 selftest.py          # 退出码 0 = 全部通过，非 0 = 有失败
    python3 selftest.py -v       # 看每条用例的名字与细节

边界：
  * 每个用例用独立的临时家目录（tempfile），绝不动 ~/mingyue；
  * 时间固定为 $MINGYUE_NOW（默认 2026-11-16T21:04:24+08:00），结果可复现；
  * 不起服务、不联网、不装包，也不碰仓库里其他文件。
  * ingest 的真解压端到端用例需要 PATH 里有 zstd（手机上有；没有就 skip，其余用例照跑）。
"""

import datetime
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
MEM = HERE / "mem.py"
SCHEMA = HERE / "schema.sql"
NOW = "2026-11-16T21:04:24+08:00"
EP = "e-20261116-001"
ZSTD = shutil.which("zstd")

# schema v1（没有 user_version / core.origin / journal.v）：迁移用例的"老库"
OLD_SCHEMA = """
CREATE TABLE episodes (id TEXT PRIMARY KEY, at TEXT NOT NULL, kind TEXT NOT NULL,
  text TEXT NOT NULL, importance REAL NOT NULL DEFAULT 0.5, source TEXT NOT NULL,
  archived_at TEXT, last_used TEXT);
CREATE TABLE facts (id TEXT PRIMARY KEY, text TEXT NOT NULL, valid_from TEXT NOT NULL,
  valid_to TEXT, confidence REAL NOT NULL DEFAULT 0.7,
  importance REAL NOT NULL DEFAULT 0.5,
  source_episode TEXT NOT NULL REFERENCES episodes(id),
  superseded_by TEXT REFERENCES facts(id), archived_at TEXT, last_used TEXT);
CREATE TABLE intentions (id TEXT PRIMARY KEY, text TEXT NOT NULL, due_at TEXT,
  status TEXT NOT NULL DEFAULT 'open',
  source_episode TEXT NOT NULL REFERENCES episodes(id), created_at TEXT NOT NULL);
CREATE TABLE core (block TEXT PRIMARY KEY, text TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE journal (seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL,
  op TEXT NOT NULL, target TEXT NOT NULL, before TEXT, after TEXT,
  reason TEXT NOT NULL, source TEXT NOT NULL);
"""

sys.path.insert(0, str(HERE))
import mem  # noqa: E402  （ingest 的纯函数级用例直接 import；CLI 用例仍走子进程）


class MemTest(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="mingyue-selftest-"))
        self.addCleanup(lambda: shutil.rmtree(self.home, ignore_errors=True))

    # ── 工具 ────────────────────────────────────────────────────────────

    def run_mem(self, *args, expect=0, env_extra=None):
        env = dict(os.environ)
        env.update({"MINGYUE_HOME": str(self.home), "MINGYUE_NOW": NOW,
                    "PYTHONIOENCODING": "utf-8",
                    # ingest 从 ~/.dsh/sessions 读，把 HOME 指到临时家目录
                    "HOME": str(self.home), "USERPROFILE": str(self.home)})
        if env_extra:
            env.update(env_extra)
        cmd = [sys.executable, str(MEM)] + [str(a) for a in args]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=env)
        if expect is not None:
            self.assertEqual(
                proc.returncode, expect,
                msg="命令 %s 期望退出码 %s，实际 %s\nstdout:\n%s\nstderr:\n%s"
                    % (" ".join(cmd[2:]), expect, proc.returncode, proc.stdout, proc.stderr))
        return proc

    def db(self):
        con = sqlite3.connect(str(self.home / "memory.db"))
        con.row_factory = sqlite3.Row
        return con

    def rows(self, sql, params=()):
        con = self.db()
        try:
            return con.execute(sql, params).fetchall()
        finally:
            con.close()

    def one(self, sql, params=()):
        return self.rows(sql, params)[0][0]

    def consolidate(self, lines, expect=0, extra=()):
        path = self.home / "cand.jsonl"
        path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n",
                        encoding="utf-8")
        return self.run_mem("consolidate", "--jsonl", path, "--reason", "测试导入",
                            *extra, expect=expect)

    def seed(self, episode_text="宿舍晚上断电，他说手机当服务器",
             fact_text="对方宿舍晚上断电"):
        """建库 + 一条情景 + 一条事实（事实必须带出处）。"""
        self.run_mem("init")
        self.run_mem("add-episode", "--kind", "chat", "--text", episode_text,
                     "--source", "session/x", "--id", EP, "--reason", "测试情景")
        return self.consolidate([{"type": "fact", "text": fact_text,
                                  "source_episode": EP, "importance": 0.6}])

    # ── ingest 工具 ─────────────────────────────────────────────────────

    def sessions_dir(self):
        return self.home / ".dsh" / "sessions"

    def workspace(self):
        return self.home / "mingyue"

    def event(self, seq, when, etype, data):
        return {"type": etype, "seq": seq,
                "time": int(when.timestamp() * 1000), "data": data}

    def text_message(self, role, source_kind, text):
        return {"role": role, "source": {"kind": source_kind},
                "content": [{"type": "text", "text": text}]}

    def write_session(self, rel, records, session_id="session-test", cwd=None,
                      header_extra=None, version=4):
        """造一个 session.v4.jsonl.zstd；有 zstd 就真压缩，没有就写明文（只给不解码的用例用）。"""
        header = {"type": "session", "version": version, "id": session_id,
                  "createdAt": 0, "cwd": str(self.workspace() if cwd is None else cwd),
                  "agentPreset": "standard"}
        if header_extra:
            header.update(header_extra)
        lines = [json.dumps(header, ensure_ascii=False)]
        lines.extend(json.dumps(record, ensure_ascii=False) for record in records)
        data = ("\n".join(lines) + "\n").encode("utf-8")
        path = self.sessions_dir() / rel / "session.v4.jsonl.zstd"
        path.parent.mkdir(parents=True, exist_ok=True)
        if ZSTD:
            proc = subprocess.run([ZSTD, "-q", "-c"], input=data,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(proc.returncode, 0,
                             msg=proc.stderr.decode("utf-8", "replace"))
            path.write_bytes(proc.stdout)
        else:
            path.write_bytes(data)
        return path

    # ── 验收 ────────────────────────────────────────────────────────────

    def test_00_init_then_check_is_green(self):
        """init 之后 check 全绿（对应验收 1）。"""
        out = self.run_mem("init")
        self.assertIn("trigram", out.stdout)
        check = self.run_mem("check")
        self.assertNotIn("[FAIL]", check.stdout)
        self.assertNotIn("[WARN]", check.stdout)
        self.assertIn("trigram", check.stdout)
        self.assertIn("外键约束有效", check.stdout)

    def test_01_fact_without_source_fails(self):
        """没有 source_episode 的 fact → 写入失败、信息可读、库不变（验收 2 + 铁律 1）。"""
        self.run_mem("init")
        proc = self.consolidate(
            [{"type": "fact", "text": "对方宿舍晚上断电", "importance": 0.6}], expect=3)
        self.assertIn("source_episode", proc.stderr)
        self.assertIn("出处", proc.stderr)
        self.assertIn("数据库未改动", proc.stderr)
        self.assertEqual(self.one("SELECT COUNT(*) FROM facts"), 0)
        self.assertEqual(self.one("SELECT COUNT(*) FROM journal"), 0)

    def test_02_chinese_two_char_search_hits(self):
        """中文检索「宿舍」能命中「对方宿舍晚上断电」（验收 3）。

        注意：FTS5 trigram 对 <3 字的词产生不了 token，这条命中靠 mem.py 的 LIKE 兜底；
        查询词 ≥3 字时才走 FTS MATCH（见 test_02b）。
        """
        self.seed()
        proc = self.run_mem("search", "宿舍", "--k", "8")
        self.assertIn("对方宿舍晚上断电", proc.stdout)
        self.assertRegex(proc.stdout, r"\[\d\.\d{2}\] \(fact f-0001")
        data = json.loads(self.run_mem("search", "宿舍", "--json").stdout)
        hits = {r["id"]: r for r in data}
        self.assertIn("f-0001", hits, msg="检索「宿舍」应命中 f-0001：%s" % proc.stdout)
        self.assertGreater(hits["f-0001"]["score"], 0)
        self.assertEqual(hits["f-0001"]["kind"], "fact")
        # MEMORY.md §5.2 的推荐写法：空格分隔的关键词（两个 2 字词）
        two = json.loads(self.run_mem("search", "宿舍 断电", "--json").stdout)
        self.assertIn("f-0001", [r["id"] for r in two])

    def test_02b_long_query_uses_fts(self):
        """≥3 字的查询词走 FTS MATCH 也能命中（证明 trigram 索引真的在用）。"""
        self.seed()
        proc = self.run_mem("search", "宿舍晚", "--json")
        data = json.loads(proc.stdout)
        self.assertTrue(any(r["id"] == EP for r in data), msg=proc.stdout)

    def test_03_duplicate_candidate_no_dup(self):
        """同一条候选导入两次 → 不产生重复条目（验收 4）。"""
        self.run_mem("init")
        lines = [
            {"type": "episode", "text": "聊到断电", "kind": "chat",
             "source": "session/x", "id": EP},
            {"type": "fact", "text": "对方宿舍晚上断电", "source_episode": EP,
             "importance": 0.6},
        ]
        self.consolidate(lines)
        self.assertEqual(self.one("SELECT COUNT(*) FROM facts"), 1)
        second = self.consolidate(lines)
        self.assertIn("[NOOP]", second.stdout)
        self.assertEqual(self.one("SELECT COUNT(*) FROM facts"), 1)
        self.assertEqual(self.one("SELECT COUNT(*) FROM episodes"), 1)
        report = self.run_mem("report", "--week").stdout
        self.assertIn("新增", report)
        self.assertIn("合并 1", report)
        self.assertIn("归档", report)

    def test_04_supersede_sets_validity(self):
        """supersede 后旧条目 valid_to 有值、新条目 superseded_by 为空（验收 5）。"""
        self.seed(fact_text="他在准备面试")
        self.consolidate([{"type": "fact", "text": "他已经面试完了",
                           "source_episode": EP, "op": "supersede", "target": "f-0001"}])
        old = self.rows("SELECT * FROM facts WHERE id='f-0001'")[0]
        new = self.rows("SELECT * FROM facts WHERE id='f-0002'")[0]
        self.assertEqual(old["valid_to"], "2026-11-16")
        self.assertEqual(old["superseded_by"], "f-0002")
        self.assertIsNone(new["superseded_by"])
        self.assertIsNone(new["valid_to"])
        self.assertEqual(new["valid_from"], "2026-11-16")
        # 旧条目默认不再出现在检索里
        data = json.loads(self.run_mem("search", "面试", "--json").stdout)
        self.assertEqual([r["id"] for r in data], ["f-0002"])
        # 同一批里对同一个目标 supersede 两次 → 整批拒绝，审计 before 不会被写脏
        before = self.one("SELECT COUNT(*) FROM facts")
        self.consolidate([
            {"type": "fact", "text": "面试结束了", "source_episode": EP,
             "op": "supersede", "target": "f-0002"},
            {"type": "fact", "text": "面试又结束了", "source_episode": EP,
             "op": "supersede", "target": "f-0002"},
        ], expect=3)
        self.assertEqual(self.one("SELECT COUNT(*) FROM facts"), before)

    def test_05_archive_hidden_then_adopt_revives(self):
        """默认检索不含归档；--include-archived 含；采用后 archived_at 变 NULL（验收 5/6）。"""
        self.seed()
        self.run_mem("forget", "f-0001", "--reason", "对方让我别再提")
        self.assertIsNotNone(self.one("SELECT archived_at FROM facts WHERE id='f-0001'"))

        hidden = json.loads(self.run_mem("search", "宿舍", "--json").stdout)
        self.assertEqual([r["id"] for r in hidden if r["kind"] == "fact"], [],
                         msg="归档的 fact 默认不该被检索到：%s" % hidden)

        shown = json.loads(self.run_mem("search", "宿舍", "--include-archived", "--json").stdout)
        facts = [r for r in shown if r["kind"] == "fact"]
        self.assertEqual([r["id"] for r in facts], ["f-0001"])
        self.assertTrue(facts[0]["archived"])
        text_out = self.run_mem("search", "宿舍", "--include-archived").stdout
        self.assertIn("已归档", text_out)

        # 没被本次命中 → 不能采用
        self.run_mem("search", "面试", "--include-archived", "--adopt", "f-0001",
                     "--reason", "采用", expect=3)
        adopted = self.run_mem("search", "宿舍", "--include-archived",
                               "--adopt", "f-0001", "--reason", "相关内容又被提起")
        self.assertIn("[ADOPT]", adopted.stdout)
        row = self.rows("SELECT * FROM facts WHERE id='f-0001'")[0]
        self.assertIsNone(row["archived_at"])
        self.assertIsNotNone(row["last_used"])

    def test_06_rebuild_from_journal_equivalent(self):
        """记录 id 集合 → 删 memory.db → 从 journal.jsonl 重建 → 一致；--check 无差异（验收 6）。"""
        self.seed()
        self.consolidate([{"type": "fact", "text": "他说手机当服务器",
                           "source_episode": EP}])
        self.run_mem("pin", "user", "- 大四，毕业设计压力大。", "--reason", "初始档案")
        self.run_mem("forget", "f-0001", "--reason", "测试归档")
        self.run_mem("render")

        before = {
            "episodes": [r["id"] for r in self.rows("SELECT id FROM episodes ORDER BY id")],
            "facts": [r["id"] for r in self.rows("SELECT id FROM facts ORDER BY id")],
            "core": [r["block"] for r in self.rows("SELECT block FROM core ORDER BY block")],
            "journal": self.one("SELECT COUNT(*) FROM journal"),
        }
        agents_before = (self.home / "AGENTS.md").read_bytes()

        (self.home / "memory.db").unlink()
        rebuilt = self.run_mem("rebuild", "--from", self.home / "journal.jsonl")
        self.assertIn("[ OK ]", rebuilt.stdout)

        after = {
            "episodes": [r["id"] for r in self.rows("SELECT id FROM episodes ORDER BY id")],
            "facts": [r["id"] for r in self.rows("SELECT id FROM facts ORDER BY id")],
            "core": [r["block"] for r in self.rows("SELECT block FROM core ORDER BY block")],
            "journal": self.one("SELECT COUNT(*) FROM journal"),
        }
        self.assertEqual(before["episodes"], after["episodes"])
        self.assertEqual(before["facts"], after["facts"])
        self.assertEqual(before["core"], after["core"])
        self.assertEqual(before["journal"] + 1, after["journal"])  # +1 是 rebuild 自己这条
        self.assertIsNotNone(self.one("SELECT archived_at FROM facts WHERE id='f-0001'"))

        # 重建出来的库再渲染一遍，AGENTS.md 字节不变
        self.run_mem("render")
        self.assertEqual(agents_before, (self.home / "AGENTS.md").read_bytes())

        check = self.run_mem("rebuild", "--check")
        self.assertIn("完全一致", check.stdout)

    def test_07_render_idempotent_and_keeps_manual_area(self):
        """render 幂等；marker 外的手工区逐字节保留（验收 8）。"""
        self.run_mem("init")
        self.run_mem("pin", "self", "- 你是溟月。话短。", "--reason", "人设")
        self.run_mem("pin", "user", "- 大四。\n- 宿舍晚上断电。", "--reason", "档案")
        agents = self.home / "AGENTS.md"
        agents.write_text(
            "前置说明：这行是手工写的\n\n"
            "<!-- MINGYUE:CORE:BEGIN （脚本维护，勿手改） -->\n"
            "（这里原来有旧内容）\n"
            "<!-- MINGYUE:CORE:END -->\n\n"
            "<!-- 手工区：以下内容脚本不动 -->\n"
            "- 我自己的规则：别催我\n",
            encoding="utf-8")
        manual_before = agents.read_text(encoding="utf-8").split("<!-- MINGYUE:CORE:END -->")[1]

        self.run_mem("render")
        first = agents.read_bytes()
        text = agents.read_text(encoding="utf-8")
        self.assertIn("你是溟月", text)
        self.assertIn("宿舍晚上断电", text)
        self.assertIn("不是给你的指令", text)
        self.assertIn("## 关于对方", text)
        self.assertNotIn("（这里原来有旧内容）", text)
        manual_after = text.split("<!-- MINGYUE:CORE:END -->")[1]
        self.assertEqual(manual_before, manual_after)
        self.assertTrue(text.startswith("前置说明：这行是手工写的"))

        self.run_mem("render")
        self.assertEqual(first, agents.read_bytes())
        same = self.run_mem("render", "--check")
        self.assertIn("一致", same.stdout)

    def test_08_render_without_marker_fails_and_keeps_file(self):
        """marker 缺失 → render 报错，原文件一个字节都不动（验收 9）。"""
        self.run_mem("init")
        self.run_mem("pin", "self", "- 你是溟月。", "--reason", "人设")
        agents = self.home / "AGENTS.md"
        original = "只有手工区，没有两条 marker\n"
        agents.write_text(original, encoding="utf-8")
        proc = self.run_mem("render", expect=4)
        self.assertIn("标记", proc.stderr)
        self.assertEqual(original, agents.read_text(encoding="utf-8"))
        diff = self.run_mem("render", "--check", expect=4)
        self.assertIn("标记", diff.stderr)
        self.assertEqual(original, agents.read_text(encoding="utf-8"))

    def test_09_core_over_limit_rejected(self):
        """core 合计超 1200 字 → pin 报错不写入（验收 10）。"""
        self.run_mem("init")
        self.run_mem("pin", "self", "字" * 700, "--reason", "人设")
        proc = self.run_mem("pin", "user", "字" * 600, "--reason", "档案", expect=3)
        self.assertIn("1200", proc.stderr)
        self.assertIn("不静默截断", proc.stderr)
        self.assertEqual(self.one("SELECT COUNT(*) FROM core"), 1)
        self.assertEqual(self.one("SELECT length(text) FROM core WHERE block='self'"), 700)
        # 刚好 1200 能写
        self.run_mem("pin", "user", "字" * 500, "--reason", "档案")
        self.assertEqual(self.one("SELECT SUM(length(text)) FROM core"), 1200)

    def test_10_bad_jsonl_rejects_whole_file(self):
        """故意喂错的 JSONL → 整批拒绝，数据库不变（对应 §8 验收 10）。"""
        self.run_mem("init")
        self.run_mem("add-episode", "--kind", "chat", "--text", "正常情景",
                     "--source", "session/x", "--id", EP, "--reason", "测试")
        path = self.home / "cand.jsonl"
        path.write_text(
            json.dumps({"type": "fact", "text": "该写进去", "source_episode": EP},
                       ensure_ascii=False) + "\n"
            + "这一行根本不是 JSON\n"
            + json.dumps({"type": "nonsense", "text": "x"}, ensure_ascii=False) + "\n",
            encoding="utf-8")
        journal_before = self.one("SELECT COUNT(*) FROM journal")
        proc = self.run_mem("consolidate", "--jsonl", path, "--reason", "测试", expect=3)
        self.assertIn("第 2 行", proc.stderr)
        self.assertIn("第 3 行", proc.stderr)
        self.assertEqual(self.one("SELECT COUNT(*) FROM facts"), 0)
        self.assertEqual(self.one("SELECT COUNT(*) FROM journal"), journal_before)


    def test_11_search_without_fts_falls_back_to_like(self):
        """没有 mem_fts 时（模拟没编译 FTS5 的 SQLite）检索仍命中，check 报 WARN 不报 FAIL。"""
        self.seed()
        con = self.db()
        con.execute("DROP TABLE mem_fts")
        con.commit()
        con.close()

        data = json.loads(self.run_mem("search", "宿舍", "--json").stdout)
        self.assertIn("f-0001", [r["id"] for r in data])
        check = self.run_mem("check")
        self.assertIn("[WARN]", check.stdout)
        self.assertNotIn("[FAIL]", check.stdout)
        self.assertIn("LIKE", check.stdout)
        # 没有 FTS 也照样能写
        self.consolidate([{"type": "fact", "text": "他说手机当服务器",
                           "source_episode": EP}])
        self.assertEqual(self.one("SELECT COUNT(*) FROM facts"), 2)

    # ── ingest：验收（2026-11-17 口径）─────────────────────────────────

    def test_12_ingest_header_and_version_guard(self):
        """会话头：v4 认；v3 / 冲突 / 缺失 / 坏 JSON 都报错（不返回空候选）。"""
        ok = mem.parse_session_header(json.dumps(
            {"type": "session", "version": 4, "id": "session-a"}), "x")
        self.assertEqual(ok["id"], "session-a")
        ok = mem.parse_session_header(json.dumps(
            {"type": "session", "sessionFormatVersion": 4, "id": "session-b"}), "x")
        self.assertEqual(ok["id"], "session-b")
        for payload in (
            {"type": "session", "version": 3, "id": "s"},
            {"type": "session", "version": 4, "sessionFormatVersion": 3, "id": "s"},
            {"type": "session", "id": "s"},
            {"type": "not-session", "version": 4, "id": "s"},
        ):
            with self.assertRaises(mem.MemError) as caught:
                mem.parse_session_header(json.dumps(payload, ensure_ascii=False), "x")
            self.assertEqual(caught.exception.code, mem.EXIT_STATE)
        with self.assertRaises(mem.MemError):
            mem.parse_session_header("这不是 JSON", "x")

    def test_13_ingest_extract_filters_and_tool_lines(self):
        """只收真人 user/message 与 assistant 正文；注入/工具正文/reasoning/跨天都丢掉。"""
        day = datetime.date(2026, 11, 16)
        header = {"type": "session", "version": 4, "id": "session-x"}
        records = [
            self.event(1, datetime.datetime(2026, 11, 16, 9, 30), "user/message",
                       self.text_message("user", "user", "昨晚聊了\n毕业设计")),
            self.event(2, datetime.datetime(2026, 11, 16, 9, 30), "user/message",
                       self.text_message("user", "agent-instructions", "AGENTS.md 注入")),
            self.event(3, datetime.datetime(2026, 11, 16, 9, 31), "assistant/message",
                       {"message": {"role": "assistant", "content": [
                           {"type": "reasoning", "text": "想一想"},
                           {"type": "text", "text": "那就慢慢来"},
                           {"type": "tool-call", "name": "pwsh", "arguments": "{}"}]}}),
            self.event(4, datetime.datetime(2026, 11, 16, 9, 31), "tool/call",
                       {"name": "pwsh", "arguments": "SECRET_ARGS"}),
            self.event(5, datetime.datetime(2026, 11, 16, 9, 31), "tool/result",
                       {"message": {"role": "tool", "content": [
                           {"type": "text", "text": "SECRET_OUTPUT"}]}}),
            self.event(6, datetime.datetime(2026, 11, 15, 23, 59), "user/message",
                       self.text_message("user", "user", "昨天的话")),
        ]
        session = mem.extract_session(header, records, day, "x")
        self.assertEqual(session["id"], "session-x")
        self.assertEqual(session["human"], 1)
        self.assertEqual([(role, text) for _when, role, text in session["entries"]],
                         [("对方", "昨晚聊了 毕业设计"),
                          ("溟月", "那就慢慢来"),
                          ("工具", "pwsh")])
        # 当天没有真人消息 → 整段跳过（防自喂）
        self.assertIsNone(mem.extract_session(header, records[1:], day, "x"))

    def test_14_ingest_render_header_line_and_truncation(self):
        """输出含 [会话 <id>]、[HH:MM] 角色: 文本；超长保头、末尾注明截断。"""
        session = {"id": "session-abc", "entries": [
            (datetime.datetime(2026, 11, 16, 21, 0), "对方", "今天有点累"),
            (datetime.datetime(2026, 11, 16, 21, 1), "溟月", "那就早点睡"),
        ]}
        text, omitted = mem.render_transcript([session], 60000)
        self.assertIsNone(omitted)
        lines = text.splitlines()
        self.assertEqual(lines[0], "[会话 session-abc]")
        self.assertEqual(lines[1], "[21:00] 对方: 今天有点累")
        self.assertEqual(lines[2], "[21:01] 溟月: 那就早点睡")
        text, omitted = mem.render_transcript([session], 20)
        self.assertIsNotNone(omitted)
        self.assertGreater(omitted, 0)
        self.assertTrue(text.splitlines()[0].startswith("[会话 "))
        self.assertTrue(text.splitlines()[-1].startswith("[截断] 超过上限 20 字"))

    def test_15_ingest_missing_zstd_is_loud(self):
        """找不到 zstd → 退出码 4 + 可读错误，不静默跳过。"""
        self.write_session("proj/sess", records=[], session_id="session-nozstd")
        proc = self.run_mem("ingest", "--day", "2026-11-16", expect=4,
                            env_extra={"PATH": ""})
        self.assertIn("找不到 zstd", proc.stderr)
        self.assertEqual(proc.stdout.strip(), "")

    def test_16_ingest_missing_sessions_dir_is_loud(self):
        """会话根不存在（~/.dsh/sessions）→ 退出码 4 + 可读错误。"""
        proc = self.run_mem("ingest", "--day", "2026-11-16", expect=4)
        self.assertIn("找不到会话目录", proc.stderr)

    def test_17_ingest_empty_day_is_explicit(self):
        """当天没有可抽取的对话 → 退出码 0，stdout 空，stderr 说清楚。"""
        (self.home / ".dsh" / "sessions").mkdir(parents=True)
        proc = self.run_mem("ingest", "--day", "2026-11-16")
        self.assertEqual(proc.stdout.strip(), "")
        self.assertIn("当天没有可抽取的对话", proc.stderr)

    def test_18_ingest_bad_workspace_is_loud(self):
        """显式 --workspace 不存在 → 退出码 4（防手误，不静默返回空）。"""
        self.write_session("proj/sess", records=[])
        proc = self.run_mem("ingest", "--workspace", self.home / "nope", expect=4)
        self.assertIn("--workspace 不是目录", proc.stderr)

    @unittest.skipUnless(ZSTD, "本机没有 zstd：真解压端到端在手机上跑")
    def test_19_ingest_end_to_end(self):
        """真 zstd 文件：cwd/日期/注入/工具/无真人会话/任务预设 全链路。"""
        ws = self.workspace()
        base = datetime.datetime(2026, 11, 16, 9, 30)
        records = [
            self.event(1, base, "user/message",
                       self.text_message("user", "user", "昨晚聊了\n毕业设计 他说很难")),
            self.event(2, base.replace(minute=31), "assistant/message",
                       {"message": {"role": "assistant", "content": [
                           {"type": "reasoning", "text": "想一想"},
                           {"type": "text", "text": "那就慢慢来"},
                           {"type": "tool-call", "name": "pwsh"}]}}),
            self.event(3, base.replace(minute=31), "tool/call",
                       {"name": "pwsh", "arguments": "SECRET_ARGS"}),
            self.event(4, base.replace(minute=31), "tool/result",
                       {"message": {"role": "tool", "content": [
                           {"type": "text", "text": "SECRET_TOOL_OUTPUT"}]}}),
            self.event(5, base.replace(minute=32), "user/message",
                       self.text_message("user", "agent-instructions",
                                         "AGENTS.md SECRET_INJECTED")),
            self.event(6, datetime.datetime(2026, 11, 15, 23, 59), "user/message",
                       self.text_message("user", "user", "昨天的话")),
        ]
        self.write_session("proj/good", records, session_id="session-good", cwd=ws)
        self.write_session("proj/other",
                           [self.event(1, base, "user/message",
                                       self.text_message("user", "user", "别的工作区"))],
                           session_id="session-other", cwd=self.home / "elsewhere")
        self.write_session("proj/nohuman",
                           [self.event(1, base, "assistant/message",
                                       {"message": {"role": "assistant", "content": [
                                           {"type": "text", "text": "任务输出"}]}})],
                           session_id="session-nohuman", cwd=ws)
        self.write_session("proj/task",
                           [self.event(1, base, "user/message",
                                       self.text_message("user", "user", "任务会话"))],
                           session_id="session-task", cwd=ws,
                           header_extra={"agentPreset": "mingyue-memory"})

        proc = self.run_mem("ingest", "--day", "2026-11-16")
        self.assertIn("[会话 session-good]", proc.stdout)
        self.assertIn("[09:30] 对方: 昨晚聊了 毕业设计 他说很难", proc.stdout)
        self.assertIn("[09:31] 溟月: 那就慢慢来", proc.stdout)
        self.assertIn("[09:31] 工具: pwsh", proc.stdout)
        for hidden in ("SECRET_ARGS", "SECRET_TOOL_OUTPUT", "SECRET_INJECTED",
                       "昨天的话", "别的工作区", "任务输出", "任务会话"):
            self.assertNotIn(hidden, proc.stdout)
        self.assertIn("工作区 1", proc.stderr)
        self.assertIn("任务预设 1", proc.stderr)
        self.assertIn("当天无真人消息 1", proc.stderr)

        truncated = self.run_mem("ingest", "--day", "2026-11-16", "--max-chars", "60")
        self.assertIn("[截断] 超过上限 60 字", truncated.stdout)
        self.assertTrue(truncated.stdout.rstrip().endswith("）。"))

    @unittest.skipUnless(ZSTD, "本机没有 zstd：真解压端到端在手机上跑")
    def test_20_ingest_unknown_header_version_is_loud(self):
        """v4 文件名但文件头是 v3 → 退出码 4、说明版本，不返回空候选。"""
        self.write_session("proj/bad", records=[], session_id="session-bad", version=3)
        proc = self.run_mem("ingest", "--day", "2026-11-16", expect=4)
        self.assertIn("不认识的会话格式版本", proc.stderr)
        self.assertIn("version=3", proc.stderr)
        self.assertEqual(proc.stdout.strip(), "")

    @unittest.skipUnless(ZSTD, "本机没有 zstd：真解压端到端在手机上跑")
    def test_20b_ingest_memory_scopes(self):
        """memory-scopes.json：include 里的工作区都抽，exclude 里的跳过（docs/mingyue/WORKSPACES.md）。"""
        chat_dir = self.home / "chat"
        private = self.home / "private"
        for d in (self.workspace(), chat_dir, private):
            d.mkdir(parents=True, exist_ok=True)
        (self.home / "memory-scopes.json").write_text(json.dumps({
            "include": [str(self.workspace()), str(chat_dir)],
            "exclude": [str(private)],
        }), encoding="utf-8")
        base = datetime.datetime(2026, 11, 16, 9, 0)
        for name, cwd, text in (
            ("main", self.workspace(), "主工作区的话"),
            ("chat", chat_dir, "正经工作区的话"),
            ("private", private, "隐私工作区的话"),
        ):
            self.write_session(
                "proj/" + name,
                [self.event(1, base, "user/message",
                            self.text_message("user", "user", text))],
                session_id="session-" + name, cwd=cwd)
        proc = self.run_mem("ingest", "--day", "2026-11-16")
        self.assertIn("主工作区的话", proc.stdout)
        self.assertIn("正经工作区的话", proc.stdout)
        self.assertNotIn("隐私工作区的话", proc.stdout)
        self.assertIn("工作区 1", proc.stderr)

    def test_20c_ingest_bad_scopes_is_loud(self):
        """memory-scopes.json 格式错 → 退出码 4，不静默退回单工作区。"""
        (self.home / "memory-scopes.json").write_text('{"include": []}', encoding="utf-8")
        (self.home / ".dsh" / "sessions").mkdir(parents=True, exist_ok=True)
        proc = self.run_mem("ingest", "--day", "2026-11-16", expect=4)
        self.assertIn("include 必须是非空数组", proc.stderr)

    # ── schema v2 / core-refresh：验收 ────────────────────────────────

    def test_21_schema_v2_migrates_legacy_db_in_place(self):
        """旧库（user_version=0）→ init 原地迁移到 v2：加列、保留数据、幂等。"""
        con = sqlite3.connect(str(self.home / "memory.db"))
        con.executescript(OLD_SCHEMA)
        con.execute("INSERT INTO episodes(id, at, kind, text, source)"
                    " VALUES('e-old','2026-11-01','chat','旧情景','session/x')")
        con.execute("INSERT INTO facts(id, text, valid_from, source_episode)"
                    " VALUES('f-0001','旧事实','2026-11-01','e-old')")
        con.execute("INSERT INTO core(block, text, updated_at)"
                    " VALUES('self','你是溟月。','2026-11-01T00:00:00+08:00')")
        con.execute("INSERT INTO journal(seq, at, op, target, reason, source)"
                    " VALUES(1,'2026-11-01T00:00:00+08:00','pin','self','旧库','cli:test')")
        con.commit()
        self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 0)
        con.close()

        # 迁移前业务命令明确拒绝（不静默跑旧 schema）
        blocked = self.run_mem("search", "旧", expect=4)
        self.assertIn("旧 schema", blocked.stderr)

        out = self.run_mem("init")
        self.assertIn("已升级", out.stdout)
        self.assertIn("schema v2", out.stdout)
        self.assertEqual(self.one("PRAGMA user_version"), 2)
        self.assertIn("origin", [r["name"] for r in self.rows("PRAGMA table_info(core)")])
        self.assertIn("v", [r["name"] for r in self.rows("PRAGMA table_info(journal)")])
        self.assertEqual(self.one("SELECT COUNT(*) FROM facts"), 1)
        self.assertEqual(self.one("SELECT origin FROM core WHERE block='self'"), "manual")
        self.assertEqual(self.one("SELECT v FROM journal WHERE seq=1"), 1)

        again = self.run_mem("init")
        self.assertIn("无需迁移", again.stdout)
        self.assertEqual(self.one("PRAGMA user_version"), 2)
        self.assertEqual(self.one("SELECT COUNT(*) FROM facts"), 1)
        check = self.run_mem("check")
        self.assertNotIn("[FAIL]", check.stdout)
        self.assertIn("user_version=2", check.stdout)

    def test_22_newer_schema_is_refused(self):
        """user_version 比脚本新 → init 拒绝，不动数据。"""
        con = sqlite3.connect(str(self.home / "memory.db"))
        con.executescript(OLD_SCHEMA)
        con.execute("INSERT INTO core(block, text, updated_at) VALUES('self','x','2026-11-01')")
        con.execute("PRAGMA user_version=3")
        con.commit()
        con.close()
        proc = self.run_mem("init", expect=4)
        self.assertIn("比本脚本认的", proc.stderr)
        self.assertEqual(self.one("PRAGMA user_version"), 3)
        self.assertEqual(self.one("SELECT text FROM core WHERE block='self'"), "x")

    def test_23_journal_v_version_header(self):
        """journal.jsonl 每条带 v=1；缺 v 按 1 重放；未知 v 报错。"""
        self.seed()
        sidecar = self.home / "journal.jsonl"
        records = [json.loads(line) for line in
                   sidecar.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertTrue(records)
        for rec in records:
            self.assertEqual(rec.get("v"), 1)
        self.assertEqual(self.one("SELECT COUNT(*) FROM journal WHERE v=1"),
                         self.one("SELECT COUNT(*) FROM journal"))

        stripped = []
        for rec in records:
            rec = dict(rec)
            rec.pop("v", None)
            stripped.append(json.dumps(rec, ensure_ascii=False))
        sidecar.write_text("\n".join(stripped) + "\n", encoding="utf-8")
        self.assertIn("完全一致", self.run_mem("rebuild", "--check").stdout)

        broken = [json.loads(line) for line in stripped]
        broken[0]["v"] = 2
        sidecar.write_text("\n".join(json.dumps(rec, ensure_ascii=False) for rec in broken) + "\n",
                           encoding="utf-8")
        refused = self.run_mem("rebuild", "--check", expect=4)
        self.assertIn("不认识的审计记录版本", refused.stderr)

    def test_24_core_refresh_auto_block(self):
        """core-refresh：top-8 → 3–5 句 auto 块；manual 不动；render；journal refresh；rebuild 一致。"""
        self.run_mem("init")
        self.run_mem("add-episode", "--kind", "chat", "--text", "今天聊了很多",
                     "--source", "session/x", "--id", EP, "--reason", "测试")
        facts = [
            ("对方宿舍晚上断电", 0.99), ("对方在准备毕业设计", 0.95),
            ("对方要去面试", 0.90), ("对方喜欢猫", 0.85),
            ("他室友在考研", 0.80), ("对方最近总熬夜", 0.75),
            ("对方拿旧手机当服务器", 0.70), ("对方嫌食堂难吃", 0.65),
            ("低重要一", 0.10), ("低重要二", 0.05),
        ]
        self.consolidate([{"type": "fact", "text": text, "source_episode": EP,
                           "importance": importance} for text, importance in facts])
        self.run_mem("pin", "self", "- 你是溟月。话短。", "--reason", "人设")
        self.run_mem("pin", "user", "- 大四。", "--reason", "档案")
        self.run_mem("forget", "f-0009", "--reason", "旧事归档，不该进 auto")

        out = self.run_mem("core-refresh")
        self.assertIn("[REFRESH]", out.stdout)
        self.assertIn("新建", out.stdout)          # 首次 core-refresh 会新建 AGENTS.md
        auto = self.rows("SELECT block, text, origin FROM core WHERE block='auto'")[0]
        self.assertEqual(auto["origin"], "auto")
        text = auto["text"]
        for kept in ("断电", "毕业设计", "面试", "熬夜", "服务器", "室友在考研"):
            self.assertIn(kept, text)
        for dropped in ("低重要一", "低重要二"):
            self.assertNotIn(dropped, text)
        sentences = [part for part in text.split("。") if part.strip()]
        self.assertEqual(len(sentences), 4)      # 8 条 → 两句一句 → 4 句
        self.assertLessEqual(len(text), 600)
        self.assertEqual(self.one("SELECT text FROM core WHERE block='self'"),
                         "- 你是溟月。话短。")
        self.assertEqual(self.one("SELECT text FROM core WHERE block='user'"), "- 大四。")
        refresh = self.rows("SELECT * FROM journal WHERE op='refresh' ORDER BY seq DESC")[0]
        self.assertEqual(refresh["target"], "auto")
        self.assertEqual(refresh["v"], 1)
        agents = (self.home / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("## 最近", agents)
        self.assertIn("你是溟月", agents)
        self.assertLessEqual(self.one("SELECT SUM(length(text)) FROM core"), 1200)
        self.assertNotIn("[FAIL]", self.run_mem("check").stdout)

        again = self.run_mem("core-refresh")
        self.assertIn("[NOOP]", again.stdout)
        self.assertEqual(self.one("SELECT COUNT(*) FROM journal WHERE op='refresh'"), 1)
        self.assertIn("完全一致", self.run_mem("rebuild", "--check").stdout)

        # 手工把 auto 标成 manual → 脚本不覆盖
        con = self.db()
        con.execute("UPDATE core SET origin='manual', text='手工接管' WHERE block='auto'")
        con.commit()
        con.close()
        takeover = self.run_mem("core-refresh")
        self.assertIn("manual", takeover.stdout)
        self.assertEqual(self.one("SELECT text FROM core WHERE block='auto'"), "手工接管")

    def test_25_core_refresh_manual_priority_budget(self):
        """manual 先占额度：auto_cap = min(600, 1200-manual)，超了从低 importance 丢。"""
        self.run_mem("init")
        self.run_mem("add-episode", "--kind", "chat", "--text", "今天聊了很多",
                     "--source", "session/x", "--id", EP, "--reason", "测试")
        self.consolidate([{"type": "fact", "text": "要点%d：%s" % (index, "字" * 70),
                           "source_episode": EP, "importance": 0.9 - index * 0.05}
                          for index in range(4)])
        self.run_mem("pin", "self", "字" * 700, "--reason", "人设")
        self.run_mem("pin", "user", "字" * 300, "--reason", "档案")
        out = self.run_mem("core-refresh")
        self.assertIn("auto 上限 200", out.stdout)
        self.assertIn("manual 占 1000", out.stdout)
        auto_text = self.one("SELECT text FROM core WHERE block='auto'")
        self.assertLessEqual(len(auto_text), 200)
        self.assertLessEqual(self.one("SELECT SUM(length(text)) FROM core"), 1200)

    # ── decay：验收 ────────────────────────────────────────────────────

    def test_26_decay_archives_weak_only(self):
        """60 天前 importance=0.1 → 归档；0.9 受保护；今天的不动；core 不动；journal=archive。"""
        self.run_mem("init")
        self.run_mem("add-episode", "--kind", "chat", "--text", "60 天前的对话",
                     "--source", "session/x", "--id", EP,
                     "--at", "2026-09-17T21:00:00+08:00", "--importance", "0.9",
                     "--reason", "测试")
        self.run_mem("pin", "self", "- 你是溟月。", "--reason", "人设")
        self.consolidate([
            {"type": "fact", "text": "弱事实", "source_episode": EP,
             "importance": 0.1, "when": "2026-09-17"},
            {"type": "fact", "text": "重要事实", "source_episode": EP,
             "importance": 0.9, "when": "2026-09-17"},
            {"type": "fact", "text": "新事实", "source_episode": EP,
             "importance": 0.2, "when": "2026-11-16"},
        ])
        out = self.run_mem("decay")
        self.assertIn("归档 1 条", out.stdout)
        self.assertIn("[ARCHIVE] fact f-0001", out.stdout)
        self.assertIsNotNone(self.one("SELECT archived_at FROM facts WHERE id='f-0001'"))
        self.assertIsNone(self.one("SELECT archived_at FROM facts WHERE id='f-0002'"))
        self.assertIsNone(self.one("SELECT archived_at FROM facts WHERE id='f-0003'"))
        self.assertIsNone(self.one("SELECT archived_at FROM episodes WHERE id=?", (EP,)))
        # 默认检索不含，include-archived 能召回；不物理删除
        self.assertEqual(json.loads(self.run_mem("search", "弱", "--json").stdout), [])
        shown = json.loads(
            self.run_mem("search", "弱", "--include-archived", "--json").stdout)
        self.assertIn("f-0001", [row["id"] for row in shown])
        self.assertEqual(self.one("SELECT COUNT(*) FROM facts"), 3)
        archived_ops = self.rows("SELECT * FROM journal WHERE op='archive'")
        self.assertEqual(len(archived_ops), 1)
        self.assertEqual(archived_ops[0]["v"], 1)
        # core 不参与衰减
        self.assertEqual(self.one("SELECT text FROM core WHERE block='self'"), "- 你是溟月。")
        # 幂等：再跑一次 0 条
        self.assertIn("归档 0 条", self.run_mem("decay").stdout)

    def test_27_decay_last_used_and_supersede(self):
        """last_used 刷新过的旧事实不归档；被取代的不处理；core 不动。"""
        self.run_mem("init")
        self.run_mem("add-episode", "--kind", "chat", "--text", "今天聊了",
                     "--source", "session/x", "--id", EP, "--importance", "0.9",
                     "--reason", "测试")
        self.consolidate([
            {"type": "fact", "text": "旧但最近用过", "source_episode": EP,
             "importance": 0.5, "when": "2026-09-17"},
            {"type": "fact", "text": "旧且没用过", "source_episode": EP,
             "importance": 0.5, "when": "2026-09-17"},
            {"type": "fact", "text": "会被取代的旧事实", "source_episode": EP,
             "importance": 0.1, "when": "2026-09-17"},
        ])
        # 刷新 f-0001 的 last_used
        self.consolidate([{"type": "fact", "text": "旧但最近用过", "source_episode": EP,
                           "op": "noop", "target": "f-0001", "importance": 0.5}])
        # 取代 f-0003（valid_to 有值 → decay 不处理）
        self.consolidate([{"type": "fact", "text": "取代后的新事实", "source_episode": EP,
                           "op": "supersede", "target": "f-0003", "importance": 0.5}])

        out = self.run_mem("decay")
        self.assertIn("归档 1 条", out.stdout)
        self.assertIsNone(self.one("SELECT archived_at FROM facts WHERE id='f-0001'"))
        self.assertIsNotNone(self.one("SELECT archived_at FROM facts WHERE id='f-0002'"))
        self.assertIsNone(self.one("SELECT archived_at FROM facts WHERE id='f-0003'"))
        self.assertIsNotNone(self.one("SELECT valid_to FROM facts WHERE id='f-0003'"))
        self.assertIsNone(self.one("SELECT archived_at FROM facts WHERE id='f-0004'"))
        self.assertEqual(self.one("SELECT COUNT(*) FROM journal WHERE op='archive'"), 1)

    # ── import-profile / apply-manual：验收 ───────────────────────────

    def test_28_import_profile_idempotent(self):
        """me.md 列表项 → facts（都指向 e-import-profile）；幂等；加一条只加一条。"""
        self.run_mem("init")
        me = self.home / "me.md"
        me.write_text("# 关于对方\n\n- 大四，准备毕业\n- 在做一个叫溟月的 App\n- 宿舍晚上断电\n",
                      encoding="utf-8")
        out = self.run_mem("import-profile", me)
        self.assertIn("[IMPORT]", out.stdout)
        self.assertIn("新增 3", out.stdout)
        episode = self.rows("SELECT * FROM episodes WHERE id='e-import-profile'")[0]
        self.assertEqual(episode["kind"], "event")
        self.assertEqual(episode["source"], "me.md")
        facts = self.rows("SELECT * FROM facts ORDER BY id")
        self.assertEqual(len(facts), 3)
        for fact in facts:
            self.assertEqual(fact["source_episode"], "e-import-profile")
            self.assertEqual(fact["importance"], 0.9)
            self.assertEqual(fact["confidence"], 0.9)
            self.assertEqual(fact["valid_from"], "2026-11-16")
        self.assertTrue(json.loads(self.run_mem("search", "溟月", "--json").stdout))
        again = self.run_mem("import-profile", me)
        self.assertIn("[NOOP]", again.stdout)
        self.assertEqual(self.one("SELECT COUNT(*) FROM facts"), 3)
        me.write_text(me.read_text(encoding="utf-8") + "- 不吃「多喝热水」\n",
                      encoding="utf-8")
        third = self.run_mem("import-profile", me)
        self.assertIn("新增 1", third.stdout)
        self.assertEqual(self.one("SELECT COUNT(*) FROM facts"), 4)
        self.assertIn("完全一致", self.run_mem("rebuild", "--check").stdout)

    def test_29_import_profile_errors(self):
        """缺文件 / 没有列表项 / episode id 被占用 → 明确报错，库不变。"""
        self.run_mem("init")
        missing = self.run_mem("import-profile", self.home / "nope.md", expect=4)
        self.assertIn("找不到初始档案", missing.stderr)
        empty = self.home / "empty.md"
        empty.write_text("# 只有标题\n\n没有列表\n", encoding="utf-8")
        no_items = self.run_mem("import-profile", empty, expect=3)
        self.assertIn("没有列表项", no_items.stderr)
        self.assertEqual(self.one("SELECT COUNT(*) FROM facts"), 0)
        me = self.home / "me.md"
        me.write_text("- 一条\n", encoding="utf-8")
        self.run_mem("add-episode", "--kind", "chat", "--text", "占位",
                     "--source", "session/x", "--id", "e-import-profile", "--reason", "测试")
        conflict = self.run_mem("import-profile", me, expect=3)
        self.assertIn("已被占用", conflict.stderr)
        self.assertEqual(self.one("SELECT COUNT(*) FROM facts"), 0)

    def test_30_apply_manual_keeps_core_region(self):
        """apply-manual.py：persona+rules 进手工区，CORE 区不动，render 后手工区仍在。"""
        self.run_mem("init")
        self.run_mem("pin", "self", "- 你是溟月。", "--reason", "人设")
        self.run_mem("render")
        (self.home / "persona.md").write_text("# 人设\n\n- 话短。\n", encoding="utf-8")
        (self.home / "rules.md").write_text(
            "# 规则\n\n- 问旧事先 search。不许编。\n", encoding="utf-8")
        agents_before = (self.home / "AGENTS.md").read_text(encoding="utf-8")
        core_before = agents_before.split("<!-- MINGYUE:CORE:END -->")[0]
        script = HERE / "apply-manual.py"
        env = dict(os.environ)
        env.update({"MINGYUE_HOME": str(self.home), "MINGYUE_NOW": NOW,
                    "PYTHONIOENCODING": "utf-8"})
        proc = subprocess.run([sys.executable, str(script)], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", env=env)
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertIn("[MANUAL]", proc.stdout)
        agents_after = (self.home / "AGENTS.md").read_text(encoding="utf-8")
        self.assertTrue(agents_after.startswith(core_before))
        self.assertIn("话短", agents_after)
        self.assertIn("问旧事先 search。不许编。", agents_after)
        self.run_mem("render")
        self.assertIn("问旧事先 search。不许编。",
                      (self.home / "AGENTS.md").read_text(encoding="utf-8"))
        checked = subprocess.run([sys.executable, str(script), "--check"],
                                 capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", env=env)
        self.assertEqual(checked.returncode, 0, msg=checked.stdout + checked.stderr)
        self.assertIn("[ OK ]", checked.stdout)

    def test_31_resolve_day_yesterday(self):
        """--day yesterday / 昨天 → 固定时间下的前一天（凌晨定时任务用）。"""
        old_env = os.environ.get("MINGYUE_NOW")
        old_now = mem._NOW
        os.environ["MINGYUE_NOW"] = NOW
        mem._NOW = None
        try:
            self.assertEqual(mem.resolve_day("yesterday"), "2026-11-15")
            self.assertEqual(mem.resolve_day("昨天"), "2026-11-15")
            self.assertEqual(mem.resolve_day("today"), "2026-11-16")
        finally:
            mem._NOW = old_now
            if old_env is None:
                os.environ.pop("MINGYUE_NOW", None)
            else:
                os.environ["MINGYUE_NOW"] = old_env


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass
    if not MEM.exists():
        print("找不到 mem.py：%s" % MEM, file=sys.stderr)
        return 2
    if not SCHEMA.exists():
        print("找不到 schema.sql：%s" % SCHEMA, file=sys.stderr)
        return 2
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(MemTest)
    verbosity = 2 if "-v" in sys.argv else 1
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
