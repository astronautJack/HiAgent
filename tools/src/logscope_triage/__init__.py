#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""logscope_triage — Drain3 日志结构化 + 跨 run 持久化模板。

用户每次 /diag 调本脚本，模板自动存到 `templates/<profile>.json` 并跨 run 累积：
  - pre-existing 簇 = 已知模式（之前 run 见过）
  - 本次「新见」簇（change_type=cluster_created）= 潜在异常/信号，单独高亮

用法:
  logscope-triage <logfile> [--top N] [--profile NAME]
                           [--log-format auto|harmony|generic] [--json]

只喂 hilog 的 message 给 Drain3；HiSysEvent JSON + faultlog 栈帧单独结构化。
--log-format generic 跳过鸿蒙 parser，纯 Drain3 喂全行。
--json 输出结构化 JSON（给 agent 可靠解析）。
"""
import re
import json
import os
import argparse
from drain3 import TemplateMiner

__version__ = "0.2.0"

try:
    from drain3.file_persistence import FilePersistence
    _HAS_PERSIST = True
except ImportError:
    _HAS_PERSIST = False

HILOG_RE = re.compile(
    r'^(?:(\d{4})-)?(\d{1,2})-(\d{1,2})\s+(\d{2}:\d{2}:\d{2}\.\d+)\s+(\d+)\s+(\d+)\s+([DIWEF])\s+'
    r'([0-9A-Fa-f]{4,6})/([^:]+):\s*(.*)$'
)
NATIVE_RE = re.compile(
    r'^\s*#(\d+)\s+pc\s+(0x[0-9a-f]+|[0-9a-f]{4,16})\s+(\S+\.so)(\([0-9a-f]+\))?'
)
ARKTS_RE = re.compile(
    r'^\s*at\s+(\S+)(?:\s+(\S+))?\s+\(([^:]+):(\d+):(\d+)\)'
)

PROFILE_DIR = os.path.expanduser("~/.logscope/templates")
MAX_HISYSEVENTS = 5000
MAX_FAULT_FRAMES = 5000


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


def _anchors(params):
    return {k: params[k] for k in ('FILE', 'LINE', 'CALLER', 'REASON', 'MSG', 'FUNCTION') if k in params}


def main():
    ap = argparse.ArgumentParser(prog='logscope-triage')
    ap.add_argument('logfile')
    ap.add_argument('--top', type=int, default=50)
    ap.add_argument('--profile', default=None,
                    help='模板库名（默认=日志文件名去扩展名）；落 ~/.logscope/templates/<profile>.json')
    ap.add_argument('--log-format', dest='log_format', default='auto',
                    choices=['auto', 'harmony', 'generic'],
                    help='auto=鸿蒙 parser 全开（默认）；harmony=同 auto；generic=跳过鸿蒙 parser，纯 Drain3')
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
    use_harmony = args.log_format in ('auto', 'harmony')

    clusters = {}
    new_clusters = []
    hisysevents = []
    fault_frames = []
    hisysevents_truncated = False
    fault_frames_truncated = False
    line_no = 0
    fed = 0
    hilog_count = 0

    def feed(content, line_no, line, dom='', tag='', lvl='', dt='', pid='', tid=''):
        nonlocal fed
        r = miner.add_log_message(content)
        cid = r['cluster_id']
        key = _cid_str(cid)
        is_new = (r.get('change_type') == 'cluster_created')
        if key not in clusters:
            clusters[key] = {'id': key, 'template': r['template_mined'], 'size': r['cluster_size'],
                             'rep_line_no': line_no, 'rep_raw': content,
                             'domain': dom, 'tag': tag, 'level': lvl, 'is_new': is_new,
                             'first_seen': {'dt': dt, 'pid': pid, 'tid': tid}}
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

            if use_harmony and line.lstrip().startswith('{'):
                try:
                    obj = json.loads(line)
                    if 'domain' in obj and 'name' in obj:
                        if len(hisysevents) < MAX_HISYSEVENTS:
                            hisysevents.append({
                                'line': line_no, 'domain': obj.get('domain', ''),
                                'name': obj.get('name', ''), 'type': obj.get('type', ''),
                                'level': obj.get('level', ''), 'params': obj.get('params', {}),
                                'anchors': _anchors(obj.get('params', {})),
                            })
                        elif not hisysevents_truncated:
                            hisysevents_truncated = True
                        continue
                except Exception:
                    pass

            if use_harmony:
                m = HILOG_RE.match(line)
                if m:
                    year, mon, day, dt, pid, tid, lvl, dom, tag, msg = m.groups()
                    hilog_count += 1
                    feed(msg, line_no, line, dom, tag, lvl,
                         dt=f"{year or ''}-{mon}-{day} {dt}".lstrip('-'), pid=pid, tid=tid)
                    continue

                nm = NATIVE_RE.match(line)
                if nm:
                    if len(fault_frames) < MAX_FAULT_FRAMES:
                        fault_frames.append({'line': line_no, 'kind': 'native',
                                             'index': nm.group(1), 'pc': nm.group(2),
                                             'so': nm.group(3), 'build_id': nm.group(4) or ''})
                    elif not fault_frames_truncated:
                        fault_frames_truncated = True
                    continue
                am = ARKTS_RE.match(line)
                if am:
                    if len(fault_frames) < MAX_FAULT_FRAMES:
                        fault_frames.append({'line': line_no, 'kind': 'arkts',
                                             'func': am.group(1), 'module': am.group(2) or '',
                                             'file': am.group(3), 'line': int(am.group(4)),
                                             'col': int(am.group(5))})
                    elif not fault_frames_truncated:
                        fault_frames_truncated = True
                    continue

            feed(line, line_no, line)

    # ---- claimed error：FAULT hisysevent > E/F hilog > 新见簇 ----
    claimed_error = None
    for ev in hisysevents:
        if ev['type'] == 'FAULT' or ev['level'] in ('FATAL', 'CRITICAL'):
            claimed_error = f"{ev['domain']}/{ev['name']}"
            break
    if not claimed_error:
        for c in clusters.values():
            if c['level'] in ('E', 'F') and c['is_new']:
                claimed_error = c['rep_raw'][:120]
                break

    harmony_signals = {'hilog': hilog_count, 'hisysevent': len(hisysevents),
                       'fault_frame': len(fault_frames)}

    if args.as_json:
        out = {
            'version': __version__,
            'profile': args.profile,
            'db_path': db_path,
            'log_format': args.log_format,
            'line_count': line_no,
            'fed': fed,
            'cluster_count': len(clusters),
            'new_cluster_ids': new_clusters,
            'claimed_error': claimed_error,
            'harmony_signals': harmony_signals,
            'clusters': sorted(clusters.values(), key=lambda c: -c['size'])[:args.top],
            'hisysevents': hisysevents,
            'fault_frames': fault_frames,
            'truncated': {'hisysevents': hisysevents_truncated, 'fault_frames': fault_frames_truncated},
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    # ---- 人类可读输出 ----
    persist_note = f"（持久化：{db_path}，跨 run 累积）" if db_path else "（无持久化）"
    print(f"=== Drain3 结构化：{line_no} 行 / 喂 {fed} 行 → {len(clusters)} 模板簇 {persist_note} ===")
    print(f"=== 鸿蒙信号：hilog {hilog_count} / hisysevent {len(hisysevents)} / fault_frame {len(fault_frames)} ===\n")

    if new_clusters:
        print(f"=== ⚠ 本次新见 {len(new_clusters)} 簇（pre-existing 之外的新模式=潜在信号）===")
        for key in new_clusters:
            c = clusters[key]
            meta = f"dom={c['domain']} tag={c['tag']} lvl={c['level']}" if c['domain'] else 'plain'
            print(f"[c{key}] {meta}")
            print(f"    template: {c['template']}")
            print(f"    rep@L{c['rep_line_no']}: {c['rep_raw'][:120]}")
        print()

    print("=== 全部模板簇（按 size 降序）===")
    for key, c in sorted(clusters.items(), key=lambda kv: -kv[1]['size'])[:args.top]:
        meta = f"dom={c['domain']} tag={c['tag']} lvl={c['level']}" if c['domain'] else 'plain'
        tag_new = " [NEW]" if c['is_new'] else ""
        print(f"[c{key}] size={c['size']}{tag_new} {meta}")
        print(f"    template: {c['template']}")
        print(f"    rep@L{c['rep_line_no']}: {c['rep_raw'][:120]}")

    if hisysevents:
        print(f"\n=== HiSysEvent 事件（{len(hisysevents)} 条{'，已截断' if hisysevents_truncated else ''}）===")
        for ev in hisysevents:
            print(f"L{ev['line']} [{ev['type']}/{ev['level']}] {ev['domain']}/{ev['name']} 锚点={json.dumps(ev['anchors'], ensure_ascii=False)}")

    if fault_frames:
        print(f"\n=== faultlog 栈帧（{len(fault_frames)} 条{'，已截断' if fault_frames_truncated else ''}）===")
        for fr in fault_frames:
            if fr['kind'] == 'native':
                print(f"L{fr['line']} native #{fr['index']} pc={fr['pc']} so={fr['so']} buildId={fr['build_id']}")
            else:
                print(f"L{fr['line']} arkts at {fr['func']} {fr['module']} ({fr['file']}:{fr['line']}:{fr['col']})")

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
