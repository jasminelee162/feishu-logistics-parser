"""语义块恢复器 (TextBlockBuilder)

在 TextNormalizer 做基础清洗之后，TextBlockBuilder 负责恢复 PDF 文本中被错误断开的
语义块（如地址断裂、姓名断裂、电话附近断裂等），以便后续 Parser 能在干净的语义块上工作。

设计要点：
 - 不在 Parser 中做修复操作；此模块承担所有语义恢复职责
 - 采用严格且保守的规则（避免过度合并）
 - 使用正则与简单启发式判断，不依赖外部模型或 LLM
 - 提供清晰的日志以便调试
"""
from __future__ import annotations

from typing import Optional
import re
import logging

logger = logging.getLogger("TextBlockBuilder")
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(ch)
    logger.setLevel(logging.INFO)


class TextBlockBuilder:
    """将文本恢复成语义连续块的构建器。

    用法:
        builder = TextBlockBuilder()
        clean = builder.build(text)

    方法遵循保守策略：仅在非常确定的情况下合并换行，避免破坏字段结构。
    """

    # 保护字段标签，避免将标签与其值合并为一行
    _FIELD_LABELS = [
        "订单号",
        "发货单号",
        "运单号",
        "提单号",
        "单号",
        "电话",
        "联系电话",
        "收货人",
        "收货地址",
    ]

    _PROTECT_TOKEN = "__TBB_PROTECT_NL__"

    def __init__(self, logger_instance: Optional[logging.Logger] = None) -> None:
        self._logger = logger_instance or logger

    def build(self, text: str) -> str:
        """恢复语义块并返回处理后的文本。

        实现步骤：
         1. 保护关键字段的换行（例如：`订单号:\n123`）以免被误合并
         2. 应用一系列保守合并规则（姓名后缀合并、数字与中文合并、连续中文合并）
         3. 恢复被保护的换行
         4. 清理多余空格并返回
        """
        if not text:
            return text

        s = text

        # 1) 保护关键字段标签后的换行：把标签后面的换行替换为占位符
        s = self._protect_field_label_newlines(s)

        # 2) 规则化合并（按顺序：数字+号合并 -> 地址/姓名分隔 -> 姓名后缀合并 -> 中文间断行合并 -> 弱合并）
        #    我们先合并数字与中文（例如 749\n号 -> 749号），然后确保地址与姓名之间有分隔，避免解析器错将“号”作为姓名的一部分。
        s = self._merge_digit_chinese(s)
        s = self._separate_address_name(s)
        s = self._merge_name_suffix(s)
        s = self._merge_chinese_continuation(s)
        s = self._weak_safe_merge(s)

        # 3) 恢复保护的换行
        s = s.replace(self._PROTECT_TOKEN, "\n")

        # 4) 清理：折叠多空行，修剪行首尾空格
        s = re.sub(r'\n{3,}', '\n\n', s)
        s = '\n'.join([ln.rstrip() for ln in s.split('\n')])
        return s

    def _protect_field_label_newlines(self, text: str) -> str:
        """保护字段标签后的换行，避免其值被错误合并。

        例如把 `订单号:\n12345` -> `订单号:__TBB_PROTECT_NL__12345`，
        后续处理完毕再还原回换行。
        """
        s = text
        for label in self._FIELD_LABELS:
            # 匹配形如：标签[:：] 可选空格 后跟换行
            pattern = re.compile(r'(' + re.escape(label) + r'\s*[:：]?\s*)\n\s*')
            s = pattern.sub(r"\1" + self._PROTECT_TOKEN, s)
        return s

    def _merge_name_suffix(self, text: str) -> str:
        """合并姓名断裂，如 `黄\n小姐` -> `黄小姐`。

        规则尽量保守：仅当被断开的右侧为常见称谓（小姐/先生/女士/太太/老师/经理）时合并。
        保留原有前置空格（用户名与地址之间的分隔）。
        """
        suffixes = ["小姐", "先生", "女士", "太太", "老师", "经理"]
        suf_pat = '|'.join([re.escape(s) for s in suffixes])
        # 捕获前一汉字或汉字组合与换行再跟称谓
        pattern = re.compile(r'([\u4e00-\u9fff]{1,3})\s*\n\s*(' + suf_pat + r')')
        new = pattern.sub(r'\1\2', text)
        if new != text:
            self._logger.debug("[TextBlockBuilder] 合并姓名后缀: 发生替换")
        return new

    def _merge_digit_chinese(self, text: str) -> str:
        """合并数字与中文的换行，例如 `749\n号` -> `749号`。

        这是地址中常见的断行，优先合并数字后紧跟中文量词的情况。
        """
        pattern = re.compile(r'(\d+)\s*\n\s*([\u4e00-\u9fff])')
        new = pattern.sub(r'\1\2', text)
        if new != text:
            self._logger.debug("[TextBlockBuilder] 合并数字与中文断行")
        return new

    def _merge_chinese_continuation(self, text: str) -> str:
        """合并两个汉字之间的断行（保守），避免影响标签和值。

        匹配两侧均为汉字且中间仅有换行与可选空白的情况。
        """
        pattern = re.compile(r'([\u4e00-\u9fff])\s*\n\s*([\u4e00-\u9fff])')
        # 迭代替换以覆盖连续多处断行
        prev = None
        s = text
        while prev != s:
            prev = s
            s = pattern.sub(r'\1\2', s)
        return s

    def _separate_address_name(self, text: str) -> str:
        """在地址末尾的 '号' 与紧随其后的姓名之间插入一个空格，避免姓名解析时误吞地址尾字符。

        规则（保守）：仅当紧随其后的文本以姓名称谓（小姐/先生/女士等）结尾或开始时插入空格。
        例如：'武宁公路749号黄小姐' -> '武宁公路749号 黄小姐'
        """
        suffixes = ["小姐", "先生", "女士", "太太", "老师", "经理", "工", "总"]
        suf_pat = '(?:' + '|'.join([re.escape(s) for s in suffixes]) + ')' 
        # 匹配 号 紧接中文姓名（1-3字）+称谓 的情况，插入空格
        pattern = re.compile(r'(\d+号)\s*(?=[\u4e00-\u9fff]{1,3}' + suf_pat + r')')
        new = pattern.sub(r'\1 ', text)
        if new != text:
            self._logger.debug("[TextBlockBuilder] 在地址号与姓名之间插入分隔空格")
        return new

    def _weak_safe_merge(self, text: str) -> str:
        """执行弱合并：在上一行没有明显句末标点且下一行以小写字母/中文/数字开始时合并。

        这是一个保守策略，仅在很可能是单个词被拆开的情况下合并换行。
        """
        pattern = re.compile(r'([^。！？!,.，；;:\-:\n\r])\s*\n\s*([\u4e00-\u9fffA-Za-z0-9])')
        # 限制迭代次数，避免意外大范围合并
        s = text
        for _ in range(3):
            new = pattern.sub(r'\1\2', s)
            if new == s:
                break
            s = new
        return s


__all__ = ['TextBlockBuilder']
