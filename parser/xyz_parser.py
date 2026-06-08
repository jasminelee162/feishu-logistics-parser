"""
XYZ 单据解析器实现。

根据 XYZ 模版（包含"送货通知单"或"Delivery Notice"）从文本中提取字段：
    - 送货单号
    - 发货日期
    - 预估抵达日期
    - 发货地
    - 收货地址（若发货信息区域含地址则优先使用）
    - 收货人
    - 联系电话
    - 总数量
    - 总净重
    - 总毛重
    - 产品编号数量

解析实现采用正则（re），并包含详细日志输出，方便定位和迭代规则。
"""
from __future__ import annotations

import re
import logging
from typing import Optional

from models.order_model import Order


logger = logging.getLogger("XYZParser")
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(ch)
    logger.setLevel(logging.INFO)


class XYZParser:
    """XYZ 单据解析器（基于正则的骨架实现）。"""

    def _clean_text(self, text: str) -> str:
        """清洗文本，移除换行符等干扰（用于地址、电话等连续字段）"""
        return re.sub(r'\n+', '', text)
    
    def _normalize_text(self, text: str) -> str:
        """标准化文本：保留基本结构但移除多余空白"""
        return re.sub(r'\s+', ' ', text)

    def parse(self, text: str, file_name: Optional[str] = None) -> Order:
        """解析给定文本并返回 `Order` 对象。

        参数:
            text: PDF 提取的全部文本
            file_name: 可选原始文件名
        返回:
            填充字段的 `Order` 对象（未匹配的字段保留为 None）
        """
        logger.info("[XYZParser] 开始解析")

        order = Order()
        order.file_name = file_name
        order.order_type = "XYZ"

        # 清洗文本（用于地址、电话等需要连续性的字段）
        clean_text = self._clean_text(text)
        # 标准化文本（用于关键字匹配）
        normalized_text = self._normalize_text(text)

        # ========== 1) 送货单号 ==========
        m = re.search(r"送货单号[:：]?\s*([A-Za-z0-9\-]+)", clean_text)
        if not m:
            m = re.search(r"Delivery\s*Notice\s*No[:：]?\s*([A-Za-z0-9\-]+)", clean_text, re.IGNORECASE)
        if m:
            order.delivery_no = m.group(1).strip()
        logger.info("[XYZParser] 送货单号: %s", order.delivery_no)

        # ========== 2) 发货日期（完整日期格式） ==========
        m = re.search(r"发货日期[:：]?\s*(\d{4}年\d{1,2}月\d{1,2}日)", normalized_text)
        if not m:
            m = re.search(r"发货日期[:：]?\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})", normalized_text)
        if not m:
            m = re.search(r"Ship\s*Date[:：]?\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})", normalized_text, re.IGNORECASE)
        if m:
            order.ship_date = m.group(1).strip()
        logger.info("[XYZParser] 发货日期: %s", order.ship_date)

        # ========== 3) 预估抵达日期 (ETA) ==========
        m = re.search(r"(预估抵达日期|预计抵达|预计到达)[:：]?\s*(\d{4}年\d{1,2}月\d{1,2}日)", normalized_text)
        if not m:
            m = re.search(r"ETA[:：]?\s*(\d{4}[-/]\d{1,2}[-/]\d{1,2})", normalized_text, re.IGNORECASE)
        if m:
            order.eta = m.group(2) if m.lastindex == 2 else m.group(1).strip()
        logger.info("[XYZParser] 预估抵达日期: %s", order.eta)

        # ========== 4) 发货地（匹配"发货地"到"Incoterns"之间的内容） ==========
        sender_addr = None
        # 方法1：匹配"发货地"到"Incoterns"之间的内容
        m = re.search(r"发货地\s*\n([\s\S]*?)Incoterns", text)
        if m:
            sender_addr = m.group(1).strip()
            # 清理：将换行符替换为空格，压缩多余空白
            sender_addr = re.sub(r'\s+', ' ', sender_addr)
        
        # 方法2：如果没有 Incoterns，匹配"发货地"到下一个关键字
        if not sender_addr:
            m = re.search(r"发货地\s*\n([^\n]+(?:公司|有限公司)[^\n]*)", clean_text)
            if m:
                sender_addr = m.group(1).strip()
        
        # 方法3：简单匹配发货地后的一行
        if not sender_addr:
            m = re.search(r"发货地[:：]?\s*([^\n]+)", clean_text)
            if m:
                sender_addr = m.group(1).strip()
        
        if sender_addr:
            order.sender_address = sender_addr
        logger.info("[XYZParser] 发货地: %s", order.sender_address)

        # ========== 5) 收货地址 ==========
        receiver_addr = None
        
        # 方法1：匹配 送货地址：xxx 收货人：
        m_addr = re.search(r"送货地址[:：]\s*(.*?)\s*收货人[:：]", clean_text)
        if m_addr:
            receiver_addr = m_addr.group(1).strip()
            order.remark = (order.remark or "") + "地址来源=送货地址字段"
        
        # 方法2：匹配 收货地址：xxx
        if not receiver_addr:
            m_addr = re.search(r"收货地址[:：]\s*(.*?)(?:$|收货人|联系电话|电话)", clean_text)
            if m_addr:
                receiver_addr = m_addr.group(1).strip()
                order.remark = (order.remark or "") + "地址来源=收货地址字段"
        
        # 方法3：从发货信息区域提取
        if not receiver_addr:
            m_block = re.search(r"发货信息[:：]\s*([\s\S]{0,400})", clean_text)
            if m_block:
                block = m_block.group(1)
                m_addr = re.search(r"(收货地址|送货地址|地址)[:：]?\s*(.*?)(?:联系电话|电话|$)", block)
                if m_addr:
                    receiver_addr = m_addr.group(2).strip()
                    order.remark = (order.remark or "") + "地址来源=发货信息"

        if receiver_addr:
            order.receiver_address = receiver_addr
        logger.info("[XYZParser] 收货地址: %s", order.receiver_address)

        # ========== 6) 收货人 ==========
        m = re.search(r"收货人[:：]\s*(.*?)\s*联系电话", clean_text)
        if not m:
            m = re.search(r"收货人[:：]\s*(.*?)(?:$|电话|手机)", clean_text)
        if not m:
            m = re.search(r"(收货人|收货联系人|联系人)[:：]\s*([\u4e00-\u9fa5]{1,10})", clean_text)
        if m:
            name_raw = m.group(1).strip() if m.lastindex == 1 else m.group(2).strip()
            name_clean = re.sub(r'[^\u4e00-\u9fa5先生小姐女士]', '', name_raw)
            if name_clean:
                order.receiver_name = name_clean
        logger.info("[XYZParser] 收货人: %s", order.receiver_name)

        # ========== 7) 联系电话 ==========
        if not order.phone:
            m = re.search(r"联系电话[:：]?\s*(\d{11})", clean_text)
            if not m:
                m = re.search(r"电话[:：]?\s*(\d{11})", clean_text)
            if not m:
                m = re.search(r"(\d{11})", clean_text)
            if m:
                order.phone = m.group(1).strip()
        logger.info("[XYZParser] 联系电话: %s", order.phone)

        # ========== 8) 总数量 ==========
        m = re.search(r"(总数量|总件数|总数)[:：]?\s*(\d+)", normalized_text)
        if m:
            try:
                order.total_quantity = int(m.group(2))
            except Exception:
                order.total_quantity = None
        logger.info("[XYZParser] 总数量: %s", order.total_quantity)

        # ========== 9) 总净重（处理千位分隔符） ==========
        m = re.search(r"(?:总)?净重[:：]?\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:KG|kg)?", normalized_text)
        if m:
            try:
                # 移除千位分隔符
                weight_str = m.group(1).replace(',', '')
                order.net_weight = float(weight_str)
            except Exception:
                order.net_weight = None
        logger.info("[XYZParser] 总净重: %s", order.net_weight)

        # ========== 10) 总毛重（处理千位分隔符） ==========
        m = re.search(r"(?:总)?毛重[:：]?\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:KG|kg)?", normalized_text)
        if m:
            try:
                weight_str = m.group(1).replace(',', '')
                order.gross_weight = float(weight_str)
            except Exception:
                order.gross_weight = None
        logger.info("[XYZParser] 总毛重: %s", order.gross_weight)

        # ========== 11) 产品编码（只统计"产品编码"字段下面的编码） ==========
        product_codes = []
        
        # 方法1：匹配 "产品编码" 后面的编码（优先使用，最准确）
        # 匹配格式：产品编码 后面跟换行，然后是编码
        m_product_section = re.search(r"产品编码\s*\n\s*([A-Z0-9]+)", text)
        if m_product_section:
            code = m_product_section.group(1).strip()
            if code:
                product_codes.append(code)
        
        # 方法2：匹配 "产品编码" 后在同一行或下一行的编码
        if not product_codes:
            m_product_section = re.search(r"产品编码[:：]?\s*([A-Z0-9]+)", clean_text)
            if m_product_section:
                code = m_product_section.group(1).strip()
                if code:
                    product_codes.append(code)
        
        # 方法3：匹配 "产品编码" 块中的多个编码
        if not product_codes:
            m_product_section = re.search(r"产品编码\s*\n([\s\S]{0,200})", text)
            if m_product_section:
                product_section = m_product_section.group(1)
                # 提取所有6-20位的纯字母数字组合（排除常见英文单词）
                codes = re.findall(r'\b([A-Z0-9]{6,20})\b', product_section)
                # 过滤掉非产品编码的英文单词
                exclude_words = {'DANGEROUS', 'EMERGENCY', 'CONTACT', 'GOODS', 'TOTAL', 'WEIGHT'}
                for code in codes:
                    if code not in exclude_words and not code.isalpha():
                        product_codes.append(code)
        
        # 去重并保持顺序
        unique_products = []
        for code in product_codes:
            if code not in unique_products:
                unique_products.append(code)
        
        order.detail_count = len(unique_products)
        
        # ========== 详细日志输出（便于调试） ==========
        logger.info("[XYZParser] ========== 解析结果汇总 ==========")
        logger.info("[XYZParser] 发货地: %s", order.sender_address)
        logger.info("[XYZParser] 收货地址: %s", order.receiver_address)
        logger.info("[XYZParser] 收货人: %s", order.receiver_name)
        logger.info("[XYZParser] 联系电话: %s", order.phone)
        logger.info("[XYZParser] 产品编码列表: %s", unique_products)
        logger.info("[XYZParser] 产品编码数量: %d", order.detail_count)
        logger.info("[XYZParser] ====================================")

        return order


__all__ = ["XYZParser"]