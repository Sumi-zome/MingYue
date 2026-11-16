#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""溟月 · mem.py 自查（PC 和 Termux 手机都能跑，只用标准库）。

    python3 selftest.py          # 退出码 0 = 全部通过，非 0 = 有失败
    python3 selftest.py -v       # 看每条用例的名字与细节

边界：
  * 每个用例用独立的临时家目录（tempfile），绝不动 ~/mingyue；
  * 时间固定为 $MINGYUE_NOW（默认 2026-11-16T21:04:24+08:00），结果可复现；
  * 不起服务、不联网、不装包，也不碰仓库里其他文件。
"""

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


class MemTest(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="mingyue-selftest-"))
        self.addCleanup(lambda: shutil.rmtree(self.home, ignore_errors=True))

    # ── 工具 ────────────────────────────────────────────────────────────

    def run_mem(self, *args, expect=0):
        env = dict(os.environ)
        env.update({"MINGYUE_HOME": str(self.home), "MINGYUE_NOW": NOW,
                    "PYTHONIOENCODING": "utf-8"})
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
