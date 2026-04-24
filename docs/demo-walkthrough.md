# Demo 走读

真实终端输出，来自 `examples/basic/` fixture。你可以通过这样复现：

```bash
pip install -e .
cd examples/basic
rm -rf .forge
```

然后按顺序跑下面的命令。

---

## 1. `forge init`

用当前 `sp/` 初始化 `.forge/`。把当前状态视为第一次 approved 基线。

```
$ forge init
initialized .forge at /.../examples/basic/.forge

$ forge status
{
  "initialized": true,
  "manifest": {
    "approved_hash": "2132239a4399eac283fdbf13ba252a3be463aa2912c70a7fa0cb9ae5202b24b5",
    "approved_at": "2026-04-24T03:57:51+00:00",
    "version": "0.1.0"
  },
  "current_hash": "2132239a4399eac283fdbf13ba252a3be463aa2912c70a7fa0cb9ae5202b24b5",
  "drifted": false
}

$ forge diff
no changes since last approve
```

`.forge/output/` 现在有 compiled view：

```
$ ls .forge/output/
AGENTS.md  CLAUDE.md
```

---

## 2. 改一个 section，同时看两个 diff

往 `sp/section/preferences.md` 加一行：

```
$ echo "- 改公共配置前，先开 PR。" >> sp/section/preferences.md

$ forge diff
======== source diff (sp/) ========
--- approved/section/preferences.md
+++ current/section/preferences.md
@@ -9,3 +9,5 @@
 - 不确定就问。不要猜。
 - 外部事实要 ground 在 live source。
 - 不要加 emoji，除非明确要求。
+
+- 改公共配置前，先开 PR。


======== output diff ========
--- codex ---
--- approved/codex
+++ proposed/codex
@@ -18,6 +18,8 @@
 - 外部事实要 ground 在 live source。
 - 不要加 emoji，除非明确要求。
 
+- 改公共配置前，先开 PR。
+
 ## Skills
 
 ...
--- personal ---
--- approved/personal
+++ proposed/personal
@@ -19,6 +19,8 @@
 - 外部事实要 ground 在 live source。
 - 不要加 emoji，除非明确要求。
 
+- 改公共配置前，先开 PR。
+
 ## Workspace

 ...
```

两件值得注意的事：

- **Source diff** 展示了 `sp/section/preferences.md` 的原始改动。
- **Output diff** 展示了**同一个**改动落进**两个** compiled target（`CLAUDE.md` 和 `AGENTS.md`）。这就是 "一份 source → 多 runtime" 的 per-file 可视化。

---

## 3. `forge approve`

把当前 `sp/` 升级为新的 approved 基线，重建所有 output，在 changelog 追加一条。

```
$ forge approve -m "add shared-config PR rule"
approved hash=82bab7145d23 at 2026-04-24T03:57:58+00:00
  wrote .../examples/basic/.forge/output/AGENTS.md
  wrote .../examples/basic/.forge/output/CLAUDE.md

$ forge diff
no changes since last approve

$ cat .forge/changelog.md
# forge-core changelog

- 2026-04-24T03:57:51+00:00 init (hash=2132239a4399)
- 2026-04-24T03:57:58+00:00 approve (hash=82bab7145d23) — add shared-config PR rule
```

---

## 4. `forge reject` — 丢弃中途改动

做一个不想要的 edit，然后 reject：

```
$ echo "noise" >> sp/section/about-me.md

$ forge diff --source-only
======== source diff (sp/) ========
--- approved/section/about-me.md
+++ current/section/about-me.md
@@ -7,3 +7,4 @@
 我是一名后端工程师 ...
 工作语言：中文。
+noise

$ forge reject
Discard all current changes to sp/ and restore approved? [y/N]: y
restored sp/ from last approved

$ forge diff
no changes since last approve
```

---

## 5. Bench：前后结构对比

snapshot 当前状态，做一次真实改动，再 snapshot，对比。

```
$ forge bench snapshot v1
snapshot `v1` created at 2026-04-24T03:58:11+00:00
  outputs: ['AGENTS.md', 'CLAUDE.md']
  sections: 4

$ echo "- bench-runner — 跑 bench 对比 snapshot。" >> sp/section/skills.md
$ forge approve -m "add bench-runner skill"
approved hash=9d489ad17c3e ...

$ forge bench snapshot v2

$ forge bench compare v1 v2
compare v1 -> v2

# outputs
  AGENTS.md: 952B -> 1023B (+71B, +2L)
  CLAUDE.md: 1212B -> 1283B (+71B, +2L)

# section size deltas
  skills: 203B -> 274B (+71B)
```

这告诉你：

- 两个 compiled output 都正好涨了 71 bytes / 2 行（和一个新 bullet 一致）。
- 涨的完全来自 `skills` section。
- 其他 section 没受影响，没意外膨胀，没丢 section。

如果你一次改 5 个 section，但只**一个**本该变，bench 就是用来抓剩下那些不该变的地方的。

---

## 6. Bench v0.1 **不做**的

它**不**回答 "agent 是不是更聪明了"。它回答 "我这次 `sp/` 改动，在 compiled output 上是不是产生了我预期的结构变化"。这是个更弱的 claim，故意的——我们宁愿 ship 一个小而诚实的 bench，也不 ship 一个"假 LLM eval"其实就是拍脑袋。

LLM-graded eval 在 v0.3（见 [`design.md §8-9`](design.md) 和 README 里的 roadmap）。

---

## 7. 验证：真实 personal-OS vault

上面用的是玩具 fixture。要证明同样流程在真实长期内容 vault 上也工作，`examples/dxyos-validation/validate.py` 对 [`dxy_OS`](https://github.com/dxxbb/dxy_OS) 跑整个 loop——5 个 section、文件名带空格、每段 3.3KB+。摘录：

```
staged 5 sections + 2 configs into .../examples/dxyos-validation/_staging
============================================================
STEP 1/7 — load sections
  [ok] `about user` 1482B / 11L  kind=derived upstream=4
  [ok] `knowledge base` 1504B / 22L  kind=derived upstream=1
  [ok] `preference` 1530B / 24L  kind=derived upstream=2
  [ok] `skill` 487B / 7L  kind=derived upstream=1
  [ok] `workspace` 3302B / 25L  kind=derived upstream=3

STEP 4/7 — 语义等价性 vs dxyOS's SP output
  line recall CLAUDE : 93.5% (threshold 90%)
  line recall AGENTS : 93.5%
  [ok] 语义等价性 >= 90%

STEP 5/7 — per-section completeness
  [ok] 5/5 section body 出现在两个 output 里

STEP 6/7 — forge doctor
  [ok] 0 errors

STEP 7/7 — 真实内容上的 gate + bench 循环
  [ok] AGENTS.md delta +24B / +3L
  [ok] CLAUDE.md delta +24B / +3L

VALIDATION PASSED
```

你自己跑：

```bash
python examples/dxyos-validation/validate.py --dxyos-root ~/dxy_OS
```

---

*英文版见 [`demo-walkthrough.en.md`](demo-walkthrough.en.md)。*
