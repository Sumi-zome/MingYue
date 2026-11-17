-- 溟月 · 记忆库 schema v2（基线 = docs/mingyue/MEMORY.md §1–§8）
--
-- 由 `mem.py init` 逐条语句执行。不要手工 `sqlite3 memory.db < schema.sql`：
-- FTS5 或 trigram 不可用时 init 会跳过 mem_fts 并退化成 LIKE 检索。
-- 版本头是 `PRAGMA user_version`（当前 2），由 mem.py 读写；老库由 init 原地 ALTER 迁移：
--   v1 → v2 : core.origin + journal.v
--
-- 字符数口径 = SQLite length()，即 Unicode 码点；一个汉字算 1 字。
--
-- 时间格式（mem.py 写入，两种都只按前 10 位取日期）：
--   ISO8601 带偏移  episodes.at / journal.at / core.updated_at / intentions.created_at
--                   / *.archived_at / *.last_used      例：2026-11-16T21:04:24+08:00
--   纯日期          facts.valid_from / facts.valid_to  例：2026-11-16
--
-- 与 MEMORY.md §2 的差异只有 4 个补列（原表结构缺了文档自己引用的载体）+ schema v2 两列，
-- 每列下面都注了出处；其余逐字照 §2。

PRAGMA foreign_keys = ON;

-- 情景：发生了什么
CREATE TABLE IF NOT EXISTS episodes (
  id          TEXT PRIMARY KEY,
  at          TEXT NOT NULL,
  kind        TEXT NOT NULL,
  text        TEXT NOT NULL,
  importance  REAL NOT NULL DEFAULT 0.5,
  source      TEXT NOT NULL,
  -- 出处：§1「情景…永久（可归档）」/ §4.2「归档 = archived_at 非空，不搬表」/ §6 铁律 6「有遗忘」
  archived_at TEXT,
  -- 出处：§3.2「NOOP 只更新 importance 与 last_used」/ §4.2 衰减 days_since_last_used
  last_used   TEXT
);

-- 语义：什么是真的（带时序）
CREATE TABLE IF NOT EXISTS facts (
  id             TEXT PRIMARY KEY,
  text           TEXT NOT NULL,
  valid_from     TEXT NOT NULL,
  valid_to       TEXT,
  confidence     REAL NOT NULL DEFAULT 0.7,
  importance     REAL NOT NULL DEFAULT 0.5,
  source_episode TEXT NOT NULL REFERENCES episodes(id),
  superseded_by  TEXT REFERENCES facts(id),
  -- 出处：§4.2「衰减到线 → 进归档，不删；归档不参与常驻注入，仍可召回」/ §6 铁律 6
  archived_at    TEXT,
  -- 出处：§3.2「NOOP 只更新 importance 与 last_used」/ §4.2 衰减 days_since_last_used
  last_used      TEXT
);

-- 前瞻：以后要提起的事
CREATE TABLE IF NOT EXISTS intentions (
  id             TEXT PRIMARY KEY,
  text           TEXT NOT NULL,
  due_at         TEXT,
  status         TEXT NOT NULL DEFAULT 'open',
  source_episode TEXT NOT NULL REFERENCES episodes(id),
  created_at     TEXT NOT NULL
);

-- 核心：常驻上下文的那几百字（三块合计 ≤ 1200 字，由 mem.py 强制，超了报错不截断）
-- block：self | user | relationship（pin 写，origin=manual）
--        auto（core-refresh 写，origin=auto，≤600 字，manual 优先占额度）
-- origin：schema v2。manual = 人写的，脚本永不自动覆盖；auto = 脚本块
CREATE TABLE IF NOT EXISTS core (
  block      TEXT PRIMARY KEY,
  text       TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  origin     TEXT NOT NULL DEFAULT 'manual'
);

-- 审计：库内这张表是**派生视图**，真源是家目录里的 journal.jsonl
-- （每行一条记录，先 fsync 该文件再提交数据库；rebuild 只从它重放）。
-- op 取值：add | update | supersede | noop | pin | forget | adopt | rebuild | refresh | archive
-- before/after 存整行 JSON 信封（{"table":…,"row":…}），重放只依赖它，不再查别的。
-- v：schema v2。审计记录版本，缺省按 1 处理（见 docs/mingyue/MIGRATION.md §8.1）
CREATE TABLE IF NOT EXISTS journal (
  seq    INTEGER PRIMARY KEY AUTOINCREMENT,
  at     TEXT NOT NULL,
  op     TEXT NOT NULL,
  target TEXT NOT NULL,
  before TEXT,
  after  TEXT,
  reason TEXT NOT NULL,
  source TEXT NOT NULL,
  v      INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_episodes_at      ON episodes(at);
CREATE INDEX IF NOT EXISTS idx_episodes_archived ON episodes(archived_at);
CREATE INDEX IF NOT EXISTS idx_facts_valid_to   ON facts(valid_to);
CREATE INDEX IF NOT EXISTS idx_facts_archived   ON facts(archived_at);
CREATE INDEX IF NOT EXISTS idx_journal_at       ON journal(at);

-- 检索：SQLite 全文索引。
-- ⚠️ 中文必须用 trigram 分词器：默认 unicode61 不切中文，整句会被当成一个词。
-- ⚠️ trigram 的已知限制：查询词 <3 字产生不了 token（「宿舍」搜不到任何东西），
--    mem.py 对这类词改用 LIKE 兜底 —— 见 MEMORY.md §5.2。
CREATE VIRTUAL TABLE IF NOT EXISTS mem_fts USING fts5(text, ref UNINDEXED, kind UNINDEXED, tokenize='trigram');
