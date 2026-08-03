#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""logscope_triage — Drain3 日志结构化 + 跨 run 持久化模板（鸿蒙 parser + 模板样式集中可配）。

用户每次 /diag 调本脚本，模板自动存到 templates/<profile>.json 并跨 run 累积：
  - pre-existing 簇 = 已知模式（之前 run 见过）
  - 本次「新见」簇（change_type=cluster_created）= 潜在异常/信号，单独高亮

模板样式（Drain3 调参 + 错误关键词 + 路径 + top）集中在一个 config 文件配，改模板行为不动源码：
  ~/.logscope/config.json（首跑自动写默认；--config <path> 覆盖；--init-config 写默认模板；--show-config 看生效值）

用法:
  logscope-triage <logfile> [--top N] [--profile NAME]
                            [--log-format auto|harmony|generic]
                            [--drain-mode learn|inference] [--json] [--config <path>]
  logscope-triage --init-config        # 写默认 config 模板到 ~/.logscope/config.json
  logscope-triage --show-config        # 打印生效 config（默认+文件合并后）

鸿蒙 parser：喂 hilog 的 message 给 Drain3；HiSysEvent JSON + faultlog 栈帧单独结构化。
--log-format generic 跳过鸿蒙 parser，纯 Drain3 喂全行。
"""
import re
import json
import os
import hashlib
import argparse
from drain3 import TemplateMiner
from drain3.masking import RegexMaskingInstruction
from drain3.template_miner_config import TemplateMinerConfig

__version__ = "0.5.0"
DIGEST_SCHEMA_VERSION = "hiagent.log-digest.v1"

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
    r'^\s*at\s+(\S+)(?:\s+(\S+))?\s+\((.+):(\d+):(\d+)\)'
)

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.logscope/config.json")

# ---- 集中默认配置（写进 config.json 供用户改）----
DEFAULT_CONFIG = {
    "drain3": {
        "sim_th": 0.4,                 # 聚类相似度阈值（0-1，高=更严格且通常更多簇）
        "depth": 4,                    # 模板树深度（大=更细模板）
        "max_children": 100,           # 每节点最大子簇数
        "max_clusters": 2000,          # 全局簇上限，满后按 LRU 淘汰
        "extra_delimiters": [],         # 额外分词符（如 [" ", "_"]）
        "parametrize_numeric_tokens": True,  # 数字当变量占位
        "mask_prefix": "<",            # 变量占位前缀
        "mask_suffix": ">",            # 变量占位后缀
        "parameter_extraction_cache_capacity": 3000,
    },
    "masking": [
        {"regex_pattern": r"(?<![A-Za-z0-9])(\d{1,3}(?:\.\d{1,3}){3})(?![A-Za-z0-9])", "mask_with": "IP"},
        {"regex_pattern": r"\b(?i:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b", "mask_with": "UUID"},
        {"regex_pattern": r"\b(?i:0x[0-9a-f]+)\b", "mask_with": "HEX"},
        {"regex_pattern": r"\b(?i:[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})\b", "mask_with": "EMAIL"},
    ],
    "error_keywords": ["error", "exception", "fatal", "crash", "failed", "anr", "segv", "abort", "panic"],
    "profile_dir": "~/.logscope/templates",
    "top_default": 50,
}

_DRAIN3_KEY_TO_ATTR = {
    "sim_th": "drain_sim_th",
    "depth": "drain_depth",
    "max_children": "drain_max_children",
    "max_clusters": "drain_max_clusters",
    "extra_delimiters": "drain_extra_delimiters",
    "parametrize_numeric_tokens": "parametrize_numeric_tokens",
    "mask_prefix": "mask_prefix",
    "mask_suffix": "mask_suffix",
    "parameter_extraction_cache_capacity": "parameter_extraction_cache_capacity",
}

# The JSON digest is passed to an LLM skill. Keep every collection bounded.
# The raw log remains the source of truth and can be read by line when needed.
MAX_HISYSEVENTS = 200
MAX_FAULT_FRAMES = 200
MAX_KEY_LINES = 200
MAX_SYMBOLS = 200
MAX_TEMPLATE_CHARS = 500
MAX_ANCHOR_CHARS = 500


def _deep_merge(base, override):
    """递归合并：override 覆盖 base（仅 dict 递归，其余直接替换）。"""
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(config_path=None):
    """加载生效 config：默认 → config 文件合并。返回 (config, path)。"""
    path = config_path or DEFAULT_CONFIG_PATH
    file_cfg = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding='utf-8') as f:
                file_cfg = json.load(f)
        except (json.JSONDecodeError, OSError):
            file_cfg = {}
    return _deep_merge(DEFAULT_CONFIG, file_cfg), path


def write_default_config(config_path=None, force=False):
    """写默认 config 模板到 path（已存在且非 force 则不动）。"""
    path = config_path or DEFAULT_CONFIG_PATH
    if os.path.exists(path) and not force:
        return False, path
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
    return True, path


def build_miner_config(drain3_cfg):
    """把 config["drain3"] 映射到 TemplateMinerConfig 实例。"""
    c = TemplateMinerConfig()
    for k, attr in _DRAIN3_KEY_TO_ATTR.items():
        if k in drain3_cfg:
            setattr(c, attr, drain3_cfg[k])
    return c


def build_masking_instructions(items):
    """Convert JSON config entries to Drain3 masking instructions."""
    instructions = []
    for item in items or []:
        if not isinstance(item, dict) or not item.get('regex_pattern') or not item.get('mask_with'):
            continue
        pattern = item['regex_pattern']
        # Drain3 combines masks into a larger regex for parameter extraction.
        # A legacy leading global flag then becomes "not at start"; scope it.
        if pattern.startswith('(?i)'):
            pattern = f"(?i:{pattern[4:]})"
        try:
            re.compile(pattern)
        except re.error:
            continue
        instructions.append(RegexMaskingInstruction(pattern, item['mask_with']))
    return instructions


def safe_profile_name(profile):
    """Keep persistent profile files inside profile_dir on Windows and Unix."""
    cleaned = re.sub(r'[^A-Za-z0-9_.-]+', '_', profile or 'default').strip('._')
    return (cleaned or 'default')[:80]


def _cid_str(cid):
    """Drain3 cluster_id 可能是 int 或 tuple（离群行 (-1,-1)），统一成可读串。"""
    if isinstance(cid, tuple):
        return '-'.join(str(x) for x in cid)
    return str(cid)


def get_miner(profile, profile_dir, drain3_cfg, masking):
    """带持久化 + 集中配置的 TemplateMiner。返回 (miner, path_or_None)。"""
    cfg = build_miner_config(drain3_cfg)
    cfg.masking_instructions = build_masking_instructions(masking)
    if _HAS_PERSIST and profile:
        pdir = os.path.expanduser(profile_dir)
        os.makedirs(pdir, exist_ok=True)
        path = os.path.join(pdir, f"{safe_profile_name(profile)}.json")
        return TemplateMiner(persistence_handler=FilePersistence(path), config=cfg), path
    return TemplateMiner(config=cfg), None


def _anchors(params):
    return {k: params[k] for k in ('FILE', 'LINE', 'CALLER', 'REASON', 'MSG', 'FUNCTION') if k in params}


def build_digest(*, raw_file, log_format, drain_mode, line_count, clusters, hisysevents,
                 fault_frames, claimed_error, top, truncated):
    """Build the single versioned contract consumed by HiAgent skills."""
    selected_clusters = sorted(clusters.values(), key=lambda c: -c['run_count'])[:top]
    compact_clusters = [{
        'id': c['id'],
        'template': c['template'][:MAX_TEMPLATE_CHARS],
        'count': c['run_count'],
        'representative_line': c['rep_line_no'],
        'domain': c['domain'],
        'tag': c['tag'],
        'level': c['level'],
        'is_new': c['is_new'],
        'known': not c['is_new'],
        'parameter_types': c.get('parameter_types', []),
    } for c in selected_clusters]

    compact_events = []
    for ev in hisysevents:
        anchors = ev.get('anchors') or {}
        compact_events.append({
            'raw_line': ev['line'],
            'domain': ev.get('domain', ''),
            'name': ev.get('name', ''),
            'type': ev.get('type', ''),
            'level': ev.get('level', ''),
            'file': str(anchors.get('FILE', ''))[:MAX_ANCHOR_CHARS],
            'source_line': str(anchors.get('LINE', '')),
            'caller': str(anchors.get('CALLER') or anchors.get('FUNCTION') or '')[:MAX_ANCHOR_CHARS],
            'reason': str(anchors.get('REASON') or anchors.get('MSG') or '')[:MAX_ANCHOR_CHARS],
        })

    symbols = []
    seen_symbols = set()

    def add_symbol(kind, name, raw_line):
        if not name:
            return
        key = (kind, str(name))
        if key in seen_symbols:
            return
        seen_symbols.add(key)
        symbols.append({'kind': kind, 'name': str(name), 'raw_line': raw_line})

    for c in selected_clusters:
        add_symbol('hilog_tag', c.get('tag'), c.get('rep_line_no'))
    for ev in compact_events:
        add_symbol('hisysevent', f"{ev['domain']}/{ev['name']}", ev['raw_line'])
        add_symbol('function', ev.get('caller'), ev['raw_line'])
    for frame in fault_frames:
        if frame['kind'] == 'native':
            add_symbol('native_library', frame.get('so'), frame['line'])
        else:
            add_symbol('function', frame.get('func'), frame['line'])
            add_symbol('source_file', frame.get('file'), frame['line'])

    key_lines = {
        c['representative_line'] for c in compact_clusters
        if c.get('representative_line') is not None
    }
    key_lines.update(ev['raw_line'] for ev in compact_events)
    key_lines.update(frame['line'] for frame in fault_frames)

    return {
        'schema_version': DIGEST_SCHEMA_VERSION,
        'raw_file': os.path.abspath(raw_file),
        'log_format': log_format,
        'drain_mode': drain_mode,
        'line_count': line_count,
        'claimed_error': claimed_error,
        'symbols': symbols[:MAX_SYMBOLS],
        'clusters': compact_clusters,
        'hisysevent_anchors': compact_events,
        'fault_frames': fault_frames,
        'key_lines': sorted(key_lines)[:MAX_KEY_LINES],
        'truncated': {
            'clusters': len(clusters) > len(compact_clusters),
            'hisysevents': bool(truncated.get('hisysevents')),
            'fault_frames': bool(truncated.get('fault_frames')),
            'key_lines': len(key_lines) > MAX_KEY_LINES,
        },
    }


def main():
    ap = argparse.ArgumentParser(prog='logscope-triage')
    ap.add_argument('logfile', nargs='?', default=None)
    ap.add_argument('--top', type=int, default=None,
                    help=f'输出簇数上限（默认=config.top_default={DEFAULT_CONFIG["top_default"]}）')
    ap.add_argument('--profile', default=None,
                    help='模板库名（默认=日志文件名去扩展名）；落 <profile_dir>/<profile>.json')
    ap.add_argument('--log-format', dest='log_format', default='auto',
                    choices=['auto', 'harmony', 'generic'],
                    help='auto=鸿蒙 parser 全开（默认）；harmony=同 auto；generic=跳过鸿蒙 parser，纯 Drain3')
    ap.add_argument('--drain-mode', dest='drain_mode', default='learn', choices=['learn', 'inference'],
                    help='learn=在线学习并持久化；inference=只匹配已有 profile，未匹配模板视为新信号')
    ap.add_argument('--json', dest='as_json', action='store_true', help='输出结构化 JSON')
    ap.add_argument('--config', dest='config_path', default=None,
                    help=f'config 文件路径（默认={DEFAULT_CONFIG_PATH}）')
    ap.add_argument('--init-config', dest='init_config', action='store_true',
                    help='写默认 config 模板到 config 路径后退出（已有则不动）')
    ap.add_argument('--show-config', dest='show_config', action='store_true',
                    help='打印生效 config（默认+文件合并后）后退出')
    args = ap.parse_args()

    if args.init_config:
        wrote, path = write_default_config(args.config_path)
        print(f"{'已写入' if wrote else '已存在（未覆盖）'} 默认 config：{path}")
        print("编辑此文件调整模板样式（drain3 调参 / error_keywords / profile_dir / top_default）。")
        return 0

    cfg, cfg_path = load_config(args.config_path)

    if args.show_config:
        print(f"# 生效 config（来源：{cfg_path}）")
        print(json.dumps(cfg, ensure_ascii=False, indent=2))
        return 0

    if not args.logfile:
        ap.error("需提供 logfile，或用 --init-config / --show-config")

    if not os.path.isfile(args.logfile):
        msg = f"日志文件不存在: {args.logfile}"
        if args.as_json:
            print(json.dumps({"error": msg}, ensure_ascii=False))
        else:
            print(msg)
        return 1

    # 首跑自动写默认 config（让用户有「一个地方」可编辑）；静默不打断
    if not os.path.isfile(cfg_path) and not args.config_path:
        write_default_config(cfg_path)

    profile_dir = cfg.get('profile_dir', DEFAULT_CONFIG['profile_dir'])
    drain3_cfg = cfg.get('drain3', DEFAULT_CONFIG['drain3'])
    configured_top = args.top if args.top is not None else cfg.get('top_default', DEFAULT_CONFIG['top_default'])
    top = max(1, min(int(configured_top), 200))
    error_keywords = [str(k) for k in cfg.get('error_keywords', []) if str(k).strip()]
    error_re = re.compile('|'.join(re.escape(k) for k in error_keywords), re.I) if error_keywords else re.compile(r'(?!x)x')

    if args.profile is None:
        args.profile = os.path.splitext(os.path.basename(args.logfile))[0]

    miner, db_path = get_miner(args.profile, profile_dir, drain3_cfg, cfg.get('masking', []))
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
        if args.drain_mode == 'inference':
            matched = miner.match(content)
            if matched is None:
                template = miner.masker.mask(content)
                digest_id = hashlib.sha256(template.encode('utf-8')).hexdigest()[:12]
                r = {'cluster_id': f'unmatched-{digest_id}', 'cluster_size': 1,
                     'template_mined': template, 'change_type': 'cluster_created'}
            else:
                r = {'cluster_id': matched.cluster_id, 'cluster_size': matched.size,
                     'template_mined': matched.get_template(), 'change_type': 'none'}
        else:
            r = miner.add_log_message(content)
        cid = r['cluster_id']
        key = _cid_str(cid)
        is_new = (r.get('change_type') == 'cluster_created')
        try:
            parameter_types = sorted({p.mask_name for p in miner.extract_parameters(r['template_mined'], content)})
        except Exception:
            parameter_types = []
        if key not in clusters:
            clusters[key] = {'id': key, 'template': r['template_mined'], 'size': r['cluster_size'],
                             'run_count': 1,
                             'rep_line_no': line_no, 'rep_raw': content,
                             'domain': dom, 'tag': tag, 'level': lvl, 'is_new': is_new,
                             'parameter_types': parameter_types,
                             'first_seen': {'dt': dt, 'pid': pid, 'tid': tid}}
            if is_new:
                new_clusters.append(key)
        else:
            clusters[key]['size'] = r['cluster_size']
            clusters[key]['run_count'] += 1
            clusters[key]['template'] = r['template_mined']
            clusters[key]['parameter_types'] = parameter_types
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

    # ---- claimed error：FAULT hisysevent > E/F hilog 新见簇 > 错误关键词新见簇 > 任意新见簇 ----
    claimed_error = None
    for ev in hisysevents:
        if ev['type'] == 'FAULT' or ev['level'] in ('FATAL', 'CRITICAL'):
            claimed_error = f"{ev['domain']}/{ev['name']}"
            break
    ordered_clusters = sorted(
        clusters.values(),
        key=lambda c: (not c['is_new'], -c['run_count'], c['rep_line_no']),
    )
    if not claimed_error:
        for c in ordered_clusters:
            if c['level'] in ('E', 'F'):
                claimed_error = c['rep_raw'][:120]
                break
    if not claimed_error:
        for c in ordered_clusters:  # 已知错误复现也必须能成为 claimed_error
            if error_re.search(c['rep_raw']) or error_re.search(c['template']):
                claimed_error = c['rep_raw'][:120]
                break
    if not claimed_error and new_clusters:
        claimed_error = clusters[new_clusters[0]]['rep_raw'][:120]
    if not claimed_error and fault_frames:
        frame = fault_frames[0]
        claimed_error = frame.get('func') or frame.get('so') or 'fault frame'

    if args.as_json:
        out = build_digest(
            raw_file=args.logfile,
            log_format=args.log_format,
            drain_mode=args.drain_mode,
            line_count=line_no,
            clusters=clusters,
            hisysevents=hisysevents,
            fault_frames=fault_frames,
            claimed_error=claimed_error,
            top=top,
            truncated={
                'hisysevents': hisysevents_truncated,
                'fault_frames': fault_frames_truncated,
            },
        )
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    # ---- 人类可读输出 ----
    persist_note = f"（持久化：{db_path}，跨 run 累积）" if db_path else "（无持久化）"
    print(f"=== Drain3 结构化：{line_no} 行 / 喂 {fed} 行 → {len(clusters)} 模板簇 {persist_note} ===")
    print(f"=== config: {cfg_path}（sim_th={drain3_cfg.get('sim_th')} depth={drain3_cfg.get('depth')}） ===")
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

    print("=== 全部模板簇（按本次日志 count 降序）===")
    for key, c in sorted(clusters.items(), key=lambda kv: -kv[1]['run_count'])[:top]:
        meta = f"dom={c['domain']} tag={c['tag']} lvl={c['level']}" if c['domain'] else 'plain'
        tag_new = " [NEW]" if c['is_new'] else ""
        print(f"[c{key}] count={c['run_count']} learned_total={c['size']}{tag_new} {meta}")
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
