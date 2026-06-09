"""
TextNormalizer v3.1（工业稳定增强版）

修复重点：
- 解决 “749号 黄\n小姐” → “749号 黄小姐”
- 防止姓名/地址断裂
- 避免过度合并导致字段污染
"""

from __future__ import annotations
import re
from typing import Callable, List


class TextNormalizer:

    def __init__(self, extra_steps: List[Callable[[str], str]] | None = None):

        self.steps = [
            self._normalize_line_endings,
            self._remove_ocr_noise_lines,

            # ⭐关键修复（必须优先）
            self._fix_name_split,
            self._fix_address_name_split,

            self._merge_field_colon_newline,
            self._merge_chinese_newlines,

            self._merge_broken_lines_safe,

            self._collapse_blank_lines,
            self._clean_spaces,
        ]

        if extra_steps:
            self.steps.extend(extra_steps)

    # =====================================================
    # 主流程
    # =====================================================
    def normalize(self, text: str) -> str:
        if not text:
            return text

        s = text
        for step in self.steps:
            try:
                s = step(s)
            except Exception:
                pass
        return s.strip()

    # =====================================================
    # 1. 基础
    # =====================================================
    def _normalize_line_endings(self, text: str) -> str:
        return text.replace("\r\n", "\n").replace("\r", "\n")

    def _remove_ocr_noise_lines(self, text: str) -> str:
        noise_patterns = [
            r'^\s*Page.*$',
            r'^\s*第\s*\d+\s*页\s*$',
            r'^\s*End\s*$',
            r'^\s*DATE.*$',
        ]

        lines = []
        for ln in text.split("\n"):
            if any(re.match(p, ln.strip(), re.IGNORECASE) for p in noise_patterns):
                continue
            lines.append(ln)
        return "\n".join(lines)

    # =====================================================
    # ⭐核心修复1：姓名断行
    # =====================================================
    def _fix_name_split(self, text: str) -> str:
        """
        黄\n小姐 → 黄小姐
        """

        return re.sub(
            r'([\u4e00-\u9fff]{1,2})\s*\n\s*(小姐|先生|女士)',
            r'\1\2',
            text
        )

    # =====================================================
    # ⭐核心修复2：地址 + 姓名断裂（你的核心问题）
    # =====================================================
    def _fix_address_name_split(self, text: str) -> str:
        """
        749号 黄\n小姐 → 749号 黄小姐
        """

        # 规则1：数字 + 号 + 空格 + 姓名断行
        text = re.sub(
            r'(\d+号)\s*\n\s*([\u4e00-\u9fff]{1,2}(?:小姐|先生|女士))',
            r'\1\2',
            text
        )

        # 规则2：地址末尾 + 姓名断行
        text = re.sub(
            r'(号)\s*\n\s*([\u4e00-\u9fff]{1,2}(?:小姐|先生|女士))',
            r'\1\2',
            text
        )

        return text

    # =====================================================
    # 2. 字段修复
    # =====================================================
    def _merge_field_colon_newline(self, text: str) -> str:
        pattern = re.compile(r'([\u4e00-\u9fff\w\s]{1,40}[：:])\s*\n\s*')
        return pattern.sub(r"\1", text)

    # =====================================================
    # 3. 中文断行
    # =====================================================
    def _merge_chinese_newlines(self, text: str) -> str:
        pattern = re.compile(r'([\u4e00-\u9fff])\s*\n\s*([\u4e00-\u9fff])')

        prev = None
        s = text
        for _ in range(5):
            if s == prev:
                break
            prev = s
            s = pattern.sub(r"\1\2", s)
        return s

    # =====================================================
    # 4. 安全合并（弱化版）
    # =====================================================
    def _merge_broken_lines_safe(self, text: str) -> str:
        """
        只合并明显不是结构边界的换行
        """

        pattern = re.compile(
            r'([A-Za-z0-9\u4e00-\u9fff])\s*\n\s*([\u4e00-\u9fffA-Za-z0-9])'
        )

        prev = None
        s = text

        for _ in range(2):  # ⚠️降低次数，避免污染字段
            if s == prev:
                break
            prev = s
            s = pattern.sub(r"\1\2", s)

        return s

    # =====================================================
    # 5. 清理
    # =====================================================
    def _collapse_blank_lines(self, text: str) -> str:
        return re.sub(r'\n{2,}', '\n\n', text)

    def _clean_spaces(self, text: str) -> str:
        lines = [ln.strip() for ln in text.split("\n")]
        s = "\n".join(lines)
        s = re.sub(r'\s+([,，。；：:])', r'\1', s)
        s = re.sub(r' {2,}', ' ', s)
        return s