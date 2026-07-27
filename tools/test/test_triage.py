#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""logscope_triage 单元测试。

覆盖 HILOG_RE / NATIVE_RE / ARKTS_RE / _cid_str / _anchors / get_miner，
以及端到端跑 sample 日志的结构。跑法：

    uv run --with drain3 python -m unittest test.test_triage

或装好后：

    python -m unittest test.test_triage
"""
import json
import os
import sys
import tempfile
import unittest

_SRC = os.path.join(os.path.dirname(__file__), '..', 'src')
sys.path.insert(0, _SRC)

from logscope_triage import (  # noqa: E402
    HILOG_RE, NATIVE_RE, ARKTS_RE, _cid_str, _anchors, get_miner, main,
)


class TestHilogRe(unittest.TestCase):
    """Bug #1: 域标识符可任意 hex 前缀；Bug #18: 月日可单数字。"""

    def _match(self, line):
        m = HILOG_RE.match(line)
        self.assertIsNotNone(m, f"应匹配: {line}")
        return m.groups()

    def test_domain_starting_with_A(self):
        g = self._match('07-24 10:00:02.310 1200 1205 E A0D04/AVSession: msg here')
        self.assertEqual(g[7], 'A0D04')   # domain
        self.assertEqual(g[8], 'AVSession')  # tag
        self.assertEqual(g[9], 'msg here')   # msg

    def test_domain_starting_with_E(self):
        """Bug #1 回归：E0F01 须匹配（旧 [AC0D] 会漏。"""
        g = self._match('07-24 10:00:02.310 1200 1205 E E0F01/SomeTag: boom')
        self.assertEqual(g[7], 'E0F01')

    def test_domain_starting_with_B(self):
        g = self._match('07-24 10:00:02.310 1200 1205 F B0E08/Tag: fatal')
        self.assertEqual(g[7], 'B0E08')
        self.assertEqual(g[6], 'F')

    def test_domain_six_chars(self):
        g = self._match('07-24 10:00:02.310 1 2 W C0DE01/X: m')
        self.assertEqual(g[7], 'C0DE01')

    def test_single_digit_month_day(self):
        """Bug #18 回归：1-1 单数字月日须匹配（旧 \d{2} 会漏。"""
        g = self._match('1-1 00:00:00.000 1 2 I A0D04/T: x')
        self.assertEqual(g[1], '1')
        self.assertEqual(g[2], '1')

    def test_optional_year(self):
        g = self._match('2026-07-24 10:00:02.310 1 2 I A0D04/T: x')
        self.assertEqual(g[0], '2026')
        self.assertEqual(g[1], '07')

    def test_no_year(self):
        g = self._match('07-24 10:00:02.310 1 2 I A0D04/T: x')
        self.assertIsNone(g[0])

    def test_non_match(self):
        self.assertIsNone(HILOG_RE.match('not a hilog line'))


class TestNativeRe(unittest.TestCase):
    """Improvement #8: pc 值放宽。"""

    def test_classic_8hex(self):
        m = NATIVE_RE.match('  #01 pc 7f9c3a5b20 /system/lib/libuv.so(buildid=abc)')
        self.assertIsNotNone(m)
        self.assertEqual(m.group(2), '7f9c3a5b20')

    def test_0x_prefix_short(self):
        m = NATIVE_RE.match('  #02 pc 0x6f98 /x.so')
        self.assertIsNotNone(m)
        self.assertEqual(m.group(2), '0x6f98')

    def test_no_buildid(self):
        m = NATIVE_RE.match('#03 pc 7f9c3a5b /y.so')
        self.assertIsNotNone(m)
        self.assertEqual(m.group(4), None)


class TestArktsRe(unittest.TestCase):
    def test_arkts_frame(self):
        m = ARKTS_RE.match('    at foo (path/file.cpp:120:5)')
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), 'foo')
        self.assertEqual(m.group(3), 'path/file.cpp')
        self.assertEqual(m.group(4), '120')

    def test_arkts_with_module(self):
        m = ARKTS_RE.match('    at foo bar (path/file.cpp:120:5)')
        self.assertIsNotNone(m)
        self.assertEqual(m.group(2), 'bar')


class TestHelpers(unittest.TestCase):
    def test_cid_str_int(self):
        self.assertEqual(_cid_str(3), '3')

    def test_cid_str_tuple(self):
        """Bug #9：tuple cluster_id 不再打印成 (-1, -1)。"""
        self.assertEqual(_cid_str((-1, -1)), '-1--1')

    def test_anchors_extracts_known_keys(self):
        params = {'FILE': 'a.cpp', 'LINE': 10, 'NOISE': 'x', 'CALLER': 'f'}
        self.assertEqual(_anchors(params), {'FILE': 'a.cpp', 'LINE': 10, 'CALLER': 'f'})

    def test_anchors_empty(self):
        self.assertEqual(_anchors({}), {})

    def test_get_miner_no_profile(self):
        miner, path = get_miner(None)
        self.assertIsNotNone(miner)
        self.assertIsNone(path)

    def test_get_miner_with_profile(self):
        """Improvement #14：恒返回 2-tuple (miner, path_or_None)。"""
        miner, path = get_miner('test-profile-xyz')
        self.assertIsNotNone(miner)
        # path 可为 None（无 FilePersistence）或非空串
        if path is not None:
            self.assertTrue(path.endswith('test-profile-xyz.json'))


class TestEndToEnd(unittest.TestCase):
    """跑 sample 日志，验结构完整。"""

    SAMPLE = os.path.join(os.path.dirname(__file__), 'sample_harmony_avsession.log')

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile('w+', suffix='.txt', delete=False, encoding='utf-8')
        self.tmp.write('07-24 10:00:02.310 1200 1205 E A0D04/AVSession: cast start failed\n'
                       '07-24 10:00:02.400 1200 1205 E A0D04/AVSession: cast start failed\n'
                       '07-24 10:00:03.000 1 2 F E0F01/Radar: fatal x\n'
                       '{"domain":"AVSESSION","name":"CAST_BEHAVIOR","type":"FAULT","level":"FATAL",'
                       '"params":{"FILE":"avsession_radar.cpp","LINE":248,"CALLER":"StartCast"}}\n')
        self.tmp.flush()

    def tearDown(self):
        os.unlink(self.tmp.name)

    def _run(self, *extra):
        old_argv = sys.argv
        sys.argv = ['logscope-triage', self.tmp.name, '--profile', 'ut_profile', *extra]
        try:
            rc = main()
        finally:
            sys.argv = old_argv
        return rc

    def test_human_output_returns_zero(self):
        rc = self._run()
        self.assertEqual(rc, 0)

    def test_json_output_structure(self):
        """Improvement #3: --json 输出可机读。"""
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        old_argv = sys.argv
        sys.argv = ['logscope-triage', self.tmp.name, '--profile', 'ut_profile2', '--json']
        try:
            with redirect_stdout(buf):
                rc = main()
        finally:
            sys.argv = old_argv
        self.assertEqual(rc, 0)
        out = json.loads(buf.getvalue())
        self.assertEqual(out['version'], '0.2.0')
        self.assertIn('clusters', out)
        self.assertIn('hisysevents', out)
        self.assertEqual(out['hisysevents'][0]['name'], 'CAST_BEHAVIOR')
        self.assertEqual(out['hisysevents'][0]['anchors']['FILE'], 'avsession_radar.cpp')
        self.assertEqual(out['hisysevents'][0]['anchors']['LINE'], 248)
        # domain E0F01 须被 hilog 捕获（Bug #1 回归在端到端里）
        self.assertTrue(out['harmony_signals']['hilog'] >= 3)

    def test_missing_file_friendly_error(self):
        """Bug #3：文件缺失不抛原始回溯。"""
        old_argv = sys.argv
        sys.argv = ['logscope-triage', '/no/such/file.log', '--profile', 'ut_missing']
        try:
            rc = main()
        finally:
            sys.argv = old_argv
        self.assertEqual(rc, 1)


if __name__ == '__main__':
    unittest.main()
