#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""logscope_triage — Drain3 日志结构化 + 跨 run 持久化模板（通用版，无平台专用 parser）。

用户每次 /diag 调本脚本，模板自动存到 templates/<profile>.json 并跨 run 累积：
  - pre-existing 簇 = 已知模式（之前 run 见过）
  - 本次「新见」簇（change_type=cluster_created）= 潜在异常/信号，单独高亮

用法:
  logscope-triage <logfile> [--top N] [--profile NAME] [--json]

纯 Drain3 通用日志模板挖掘：喂每行给 Drain3，新见簇 = 潜在信号。
claimed_error = 含错误关键词的新见簇（error/exception/fatal/crash/failed/anr/segv/abort/panic）。
--json 输出结构化 JSON（给 agent 可靠解析）。
"""
import re
import json
import os
import argparse
from drain3 import TemplateMiner

__version__ = "0.3.0"

try:
    from drain3.file_persistence import FilePersistence
    _HAS_PERSIST = True
except ImportError:
    _HAS_PERSIST = False

PROFILE_DIR = os.path.expanduser("~/.logscope/templates")
ERROR_RE = re.compile(r'error|exception|fatal|crash|failed|anr|segv|abort|panic', re.I)


def _cid_str(cid):
    """Drain3 cluster_id 可能是 int 或 tuple（离群行 (-1,-1)），统一成可读串。"""
    if isinstance(cid, tuple):
        return '-'.join(str(x) for x in cid)
    return str(cid)


def get_miner(profile):
    """带持久化的 TemplateMiner——跨 run 累积模板。恒返回 (miner, path_or_None)。"""
    if _HAS_PERSIST and profile:
        os.makedirs(PROFILE_DIR, exist_ok=True)
        path = os.path.join(PROFILE_DIR, f"{profile}.json")
        return TemplateMiner(persistence_handler=FilePersistence(path)), path
    return TemplateMiner(), None


def _is_error(rep, template):
    return bool(ERROR_RE.search(rep) or ERROR_RE.search(template))


def main():
    ap = argparse.ArgumentParser(prog='logscope-triage')
    ap.add_argument('logfile')
    ap.add_argument('--top', type=int, default=50)
    ap.add_argument('--profile', default=None,
                    help='模板库名（默认=日志文件名去扩展名）；落 ~/.logscope/templates/<profile>.json')
    ap.add_argument('--json', dest='as_json', action='store_true',
                    help='输出结构化 JSON（给 agent 可靠解析）')
    args = ap.parse_args()

    if not os.path.isfile(args.logfile):
        msg = f"日志文件不存在: {args.logfile}"
        if args.as_json:
            print(json.dumps({"error": msg}, ensure_ascii=False))
        else:
            print(msg)
        return 1

    if args.profile is None:
        args.profile = os.path.splitext(os.path.basename(args.logfile))[0]

    miner, db_path = get_miner(args.profile)

    clusters = {}
    new_clusters = []
    line_no = 0
    fed = 0

    def feed(content, line_no):
        nonlocal fed
        r = miner.add_log_message(content)
        cid = r['cluster_id']
        key = _cid_str(cid)
        is_new = (r.get('change_type') == 'cluster_created')
        if key not in clusters:
            clusters[key] = {'id': key, 'template': r['template_mined'], 'size': r['cluster_size'],
                             'rep_line_no': line_no, 'rep_raw': content, 'is_new': is_new}
            if is_new:
                new_clusters.append(key)
        else:
            clusters[key]['size'] = r['cluster_size']
            clusters[key]['template'] = r['template_mined']
        fed += 1

    with open(args.logfile, encoding='utf-8', errors='replace') as f:
        for raw in f:
            line_no += 1
            line = raw.rstrip('\n')
            if not line.strip():
                continue
            feed(line, line_no)

    # ---- claimed error：含错误关键词的新见簇 > 任意新见簇 ----
    claimed_error = None
    for key in new_clusters:
        c = clusters[key]
        if _is_error(c['rep_raw'], c['template']):
            claimed_error = c['rep_raw'][:120]
            break
    if not claimed_error and new_clusters:
        claimed_error = clusters[new_clusters[0]]['rep_raw'][:120]

    if args.as_json:
        out = {
            'version': __version__,
            'profile': args.profile,
            'db_path': db_path,
            'line_count': line_no,
            'fed': fed,
            'cluster_count': len(clusters),
            'new_cluster_ids': new_clusters,
            'claimed_error': claimed_error,
            'clusters': sorted(clusters.values(), key=lambda c: -c['size'])[:args.top],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    # ---- 人类可读输出 ----
    persist_note = f"（持久化：{db_path}，跨 run 累积）" if db_path else "（无持久化）"
    print(f"=== Drain3 结构化：{line_no} 行 / 喂 {fed} 行 → {len(clusters)} 模板簇 {persist_note} ===\n")

    if new_clusters:
        print(f"=== ⚠ 本次新见 {len(new_clusters)} 簇（pre-existing 之外的新模式=潜在信号）===")
        for key in new_clusters:
            c = clusters[key]
            tag_err = " [ERROR]" if _is_error(c['rep_raw'], c['template']) else ""
            print(f"[c{key}]{tag_err}")
            print(f"    template: {c['template']}")
            print(f"    rep@L{c['rep_line_no']}: {c['rep_raw'][:120]}")
        print()

    print("=== 全部模板簇（按 size 降序）===")
    for key, c in sorted(clusters.items(), key=lambda kv: -kv[1]['size'])[:args.top]:
        tag_new = " [NEW]" if c['is_new'] else ""
        print(f"[c{key}] size={c['size']}{tag_new}")
        print(f"    template: {c['template']}")
        print(f"    rep@L{c['rep_line_no']}: {c['rep_raw'][:120]}")

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
