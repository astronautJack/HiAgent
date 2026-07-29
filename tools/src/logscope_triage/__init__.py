#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""logscope_triage — Drain3 日志结构化 + 跨 run 持久化模板（通用版，模板样式集中可配）。

用户每次 /diag 调本脚本，模板自动存到 templates/<profile>.json 并跨 run 累积：
  - pre-existing 簇 = 已知模式（之前 run 见过）
  - 本次「新见」簇 = 潜在异常/信号，单独高亮

模板样式（Drain3 调参 + 错误关键词 + 路径 + top）集中在一个 config 文件配，改模板行为不动源码：
  ~/.logscope/config.json（首跑自动写默认；--config <path> 覆盖；--init-config 写默认模板；--show-config 看生效值）

用法:
  logscope-triage <logfile> [--top N] [--profile NAME] [--json] [--config <path>]
  logscope-triage --init-config        # 写默认 config 模板到 ~/.logscope/config.json
  logscope-triage --show-config        # 打印生效 config（默认+文件合并后）

纯 Drain3 通用：喂每行给模板挖掘，新见簇 = 潜在信号。
claimed_error = 含错误关键词（config.error_keywords）的新见簇。
"""
import re
import json
import os
import argparse
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig

__version__ = "0.4.0"

try:
    from drain3.file_persistence import FilePersistence
    _HAS_PERSIST = True
except ImportError:
    _HAS_PERSIST = False

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.logscope/config.json")

# ---- 集中默认配置（写进 config.json 供用户改）----
DEFAULT_CONFIG = {
    "drain3": {
        "sim_th": 0.4,                 # 聚类相似度阈值（0-1，高=严少簇，低=松多簇）
        "depth": 4,                    # 模板树深度（大=更细模板）
        "max_children": 100,           # 每节点最大子簇数
        "max_clusters": None,          # 全局簇上限（None=无界）
        "extra_delimiters": [],         # 额外分词符（如 [" ", "_"]）
        "parametrize_numeric_tokens": True,  # 数字当变量占位
        "mask_prefix": "<",            # 变量占位前缀
        "mask_suffix": ">",            # 变量占位后缀
    },
    "error_keywords": ["error", "exception", "fatal", "crash", "failed", "anr", "segv", "abort", "panic"],
    "profile_dir": "~/.logscope/templates",
    "top_default": 50,
}

# config["drain3"] 键 → TemplateMinerConfig 属性名映射
_DRAIN3_KEY_TO_ATTR = {
    "sim_th": "drain_sim_th",
    "depth": "drain_depth",
    "max_children": "drain_max_children",
    "max_clusters": "drain_max_clusters",
    "extra_delimiters": "drain_extra_delimiters",
    "parametrize_numeric_tokens": "parametrize_numeric_tokens",
    "mask_prefix": "mask_prefix",
    "mask_suffix": "mask_suffix",
}


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
    """加载生效 config：默认 → config 文件合并。文件不存在则用默认（并写一份供编辑）。返回 (config, path)。"""
    path = config_path or DEFAULT_CONFIG_PATH
    file_cfg = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding='utf-8') as f:
                file_cfg = json.load(f)
        except (json.JSONDecodeError, OSError):
            file_cfg = {}  # 损坏的 config 静默回退默认
    cfg = _deep_merge(DEFAULT_CONFIG, file_cfg)
    return cfg, path


def write_default_config(config_path=None, force=False):
    """写默认 config 模板到 path（已存在且非 force 则不动）。"""
    path = config_path or DEFAULT_CONFIG_PATH
    if os.path.exists(path) and not force:
        return False, path
    os.makedirs(os.path.dirname(path), exist_ok=True)
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


def _cid_str(cid):
    """Drain3 cluster_id 可能是 int 或 tuple（离群行 (-1,-1)），统一成可读串。"""
    if isinstance(cid, tuple):
        return '-'.join(str(x) for x in cid)
    return str(cid)


def get_miner(profile, profile_dir, drain3_cfg):
    """带持久化 + 集中配置的 TemplateMiner。返回 (miner, path_or_None)。"""
    cfg = build_miner_config(drain3_cfg)
    if _HAS_PERSIST and profile:
        pdir = os.path.expanduser(profile_dir)
        os.makedirs(pdir, exist_ok=True)
        path = os.path.join(pdir, f"{profile}.json")
        return TemplateMiner(persistence_handler=FilePersistence(path), config=cfg), path
    return TemplateMiner(config=cfg), None


def main():
    ap = argparse.ArgumentParser(prog='logscope-triage')
    ap.add_argument('logfile', nargs='?', default=None)
    ap.add_argument('--top', type=int, default=None,
                    help=f'输出簇数上限（默认=config.top_default={DEFAULT_CONFIG["top_default"]}）')
    ap.add_argument('--profile', default=None,
                    help='模板库名（默认=日志文件名去扩展名）；落 <profile_dir>/<profile>.json')
    ap.add_argument('--json', dest='as_json', action='store_true', help='输出结构化 JSON')
    ap.add_argument('--config', dest='config_path', default=None,
                    help=f'config 文件路径（默认={DEFAULT_CONFIG_PATH}）')
    ap.add_argument('--init-config', dest='init_config', action='store_true',
                    help='写默认 config 模板到 config 路径后退出（已有则不动，除非先删）')
    ap.add_argument('--show-config', dest='show_config', action='store_true',
                    help='打印生效 config（默认+文件合并后）后退出')
    args = ap.parse_args()

    # --init-config：写默认模板供编辑，退出
    if args.init_config:
        wrote, path = write_default_config(args.config_path)
        print(f"{'已写入' if wrote else '已存在（未覆盖）'} 默认 config：{path}")
        print("编辑此文件调整模板样式（drain3 调参 / error_keywords / profile_dir / top_default）。")
        return 0

    # 加载生效 config
    cfg, cfg_path = load_config(args.config_path)

    # --show-config：打印生效配置，退出
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

    # 首跑自动写默认 config（让用户有「一个地方」可编辑）；静默，不打断流程
    if not os.path.isfile(cfg_path) and not args.config_path:
        write_default_config(cfg_path)

    profile_dir = cfg.get('profile_dir', DEFAULT_CONFIG['profile_dir'])
    drain3_cfg = cfg.get('drain3', DEFAULT_CONFIG['drain3'])
    top = args.top if args.top is not None else cfg.get('top_default', DEFAULT_CONFIG['top_default'])

    if args.profile is None:
        args.profile = os.path.splitext(os.path.basename(args.logfile))[0]

    miner, db_path = get_miner(args.profile, profile_dir, drain3_cfg)

    error_re = re.compile('|'.join(re.escape(k) for k in cfg.get('error_keywords', DEFAULT_CONFIG['error_keywords'])), re.I)

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

    def _is_error(rep, template):
        return bool(error_re.search(rep) or error_re.search(template))

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
            'config_path': cfg_path,
            'profile': args.profile,
            'db_path': db_path,
            'drain3': drain3_cfg,
            'line_count': line_no,
            'fed': fed,
            'cluster_count': len(clusters),
            'new_cluster_ids': new_clusters,
            'claimed_error': claimed_error,
            'clusters': sorted(clusters.values(), key=lambda c: -c['size'])[:top],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    # ---- 人类可读输出 ----
    persist_note = f"（持久化：{db_path}，跨 run 累积）" if db_path else "（无持久化）"
    print(f"=== Drain3 结构化：{line_no} 行 / 喂 {fed} 行 → {len(clusters)} 模板簇 {persist_note} ===")
    print(f"=== config: {cfg_path}（sim_th={drain3_cfg.get('sim_th')} depth={drain3_cfg.get('depth')}）===\n")

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
    for key, c in sorted(clusters.items(), key=lambda kv: -kv[1]['size'])[:top]:
        tag_new = " [NEW]" if c['is_new'] else ""
        print(f"[c{key}] size={c['size']}{tag_new}")
        print(f"    template: {c['template']}")
        print(f"    rep@L{c['rep_line_no']}: {c['rep_raw'][:120]}")

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
