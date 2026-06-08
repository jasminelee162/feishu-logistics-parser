r"""
ABC 单据解析器实现。

该模块实现 `ABCParser` 类，负责从 ABC 格式的 PDF 文本中抽取规定字段，
并返回统一的 `Order` 对象。解析采用正则（re）实现，包含必要的异常容错与日志。

提取字段：
    - 订单号（正则：订单号[:：]\s*(\d+)）
    - 发货单号（可能换行）
    - 客户要求区域：若存在则优先从中提取收货地址、收货人、联系电话，且标记地址来源为"客户要求"
    - 总净重（单位 KG）
    - 总毛重（单位 KG）
    - 产品编号统计（以 'ABC' 开头的产品编码），生成 `detail_count`

日志：
    - [ABCParser] 开始解析
    - [ABCParser] 订单号:
    - [ABCParser] 发货单号:
    - [ABCParser] 客户要求原始内容:
    - [ABCParser] 收货地址:
    - [ABCParser] 收货人:
    - [ABCParser] 联系电话:
    - [ABCParser] 总净重:
    - [ABCParser] 总毛重:
    - [ABCParser] 产品编码列表:
    - [ABCParser] 产品编码数量:
"""
from __future__ import annotations

import re
import logging
from typing import Optional

from models.order_model import Order


# ========== BaseParser 基类 ==========
class BaseParser:
    """解析器基类，定义统一的解析接口"""
    
    def parse(self, text: str, file_name: Optional[str] = None) -> Order:
        """解析文本并返回 Order 对象（子类必须实现）"""
        raise NotImplementedError("子类必须实现 parse 方法")
    
    def extract_field(self, text: str, pattern: str) -> Optional[str]:
        """辅助方法：使用正则提取字段"""
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        return match.group(1).strip() if match else None
# ========================================


logger = logging.getLogger("ABCParser")
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(ch)
    logger.setLevel(logging.INFO)


class ABCParser(BaseParser):
    """ABC 格式单据解析器（使用正则实现的基础解析器）。"""

    def _clean_text(self, text: str) -> str:
        """清洗文本，移除换行符等干扰"""
        return re.sub(r'\n+', '', text)
    
    def _normalize_text(self, text: str) -> str:
        """标准化文本：保留基本结构但移除多余空白"""
        return re.sub(r'\s+', ' ', text)

    def parse(self, text: str, file_name: Optional[str] = None) -> Order:
        """解析 ABC 单据的文本并返回 `Order` 对象。

        参数:
            text: 从 PDF 提取的全文字符串
            file_name: 可选的原始文件名

        返回:
            Order 对象（字段尽量填充，找不到的字段保持 None）
        """
        logger.info("[ABCParser] 开始解析")

        order = Order()
        order.file_name = file_name
        order.order_type = "ABC"

        # 清洗文本
        clean_text = self._clean_text(text)
        normalized_text = self._normalize_text(text)

        # ========== 1) 订单号 ==========
        m = re.search(r"订单号[:：]\s*(\d+)", text)
        if m:
            order.order_no = m.group(1)
        logger.info("[ABCParser] 订单号: %s", order.order_no)

        # ========== 2) 发货单号 ==========
        m = re.search(r"发货单号[:：]\s*(\d+)", clean_text)
        if m:
            order.delivery_no = m.group(1)
        logger.info("[ABCParser] 发货单号: %s", order.delivery_no)

        # ========== 3) 客户要求区域 -> 收货地址/人/电话 ==========
        customer_req = None
        # 先尝试从原文本中提取客户要求区域（保留原始换行）
        m = re.search(r"客户要求[:：]([\s\S]{0,800}?)(?:总净重|总毛重|订单号|发货单号|$)", text)
        if m:
            customer_req = m.group(1)
        
        if customer_req:
            # 日志输出客户要求原始内容
            logger.info("[ABCParser] 客户要求原始内容: %r", customer_req[:200])
            
            # 1. 提取联系电话（11位手机号）
            phone = None
            m_phone = re.search(r"联系电话[:：]\s*(\d{11})", customer_req)
            if not m_phone:
                # 尝试匹配更宽松的电话格式
                m_phone = re.search(r"(\d{11})", customer_req)
            if m_phone:
                phone = m_phone.group(1)
                order.phone = phone
            
            # 2. 提取送货地址区域
            # 匹配 "送货地址：" 到 "联系电话" 之间的内容
            addr_section = None
            m_addr = re.search(r"送货地址[:：](.*?)(?:联系电话|$)", customer_req, re.DOTALL)
            if m_addr:
                addr_section = m_addr.group(1).strip()
            
            if addr_section:
                # 3. 在地址区域中识别收货人（手机号前面的最后一个中文姓名）
                receiver = None
                address = addr_section
                
                # 定义收货人称谓模式
                receiver_patterns = [
                    r'([\u4e00-\u9fa5]{1,4}(?:小姐|女士|先生|经理|工|总))',  # 黄小姐、张先生、李工、王总
                    r'([\u4e00-\u9fa5]{2,4})(?=\s*$)',
                ]
                
                # 方法1：查找中文姓名 + 称谓
                for pattern in receiver_patterns:
                    # 从地址末尾开始查找
                    m_receiver = re.search(pattern, address)
                    if m_receiver:
                        receiver = m_receiver.group(1)
                        # 从地址中移除收货人
                        address = address[:m_receiver.start()].strip()
                        break
                
                # 方法2：如果没有称谓，尝试匹配地址末尾的中文姓名（2-4字）
                if not receiver:
                    # 匹配地址末尾的中文姓名（前面有数字或空格）
                    m_name = re.search(r'[\d号路街]\s*([\u4e00-\u9fa5]{2,4})$', address)
                    if m_name:
                        receiver = m_name.group(1)
                        address = address[:m_name.start()].strip()
                
                # 清理地址：移除多余的换行符和空格
                address = re.sub(r'\s+', ' ', address).strip()
                # 移除地址末尾的特殊字符
                address = re.sub(r'[，,、]$', '', address)
                
                if address:
                    order.receiver_address = address
                if receiver:
                    order.receiver_name = receiver
            
            # 标注地址来源
            if order.receiver_address or order.receiver_name or order.phone:
                order.remark = (order.remark or "") + "地址来源=客户要求"
        
        logger.info("[ABCParser] 收货地址: %s", order.receiver_address)
        logger.info("[ABCParser] 收货人: %s", order.receiver_name)
        logger.info("[ABCParser] 联系电话: %s", order.phone)

        # ========== 4) 总净重 ==========
        m = re.search(r"总净重[:：]\s*([0-9]+(?:\.[0-9]+)?)\s*(?:KG|kg)?", text)
        if m:
            try:
                order.net_weight = float(m.group(1))
            except Exception:
                order.net_weight = None
        logger.info("[ABCParser] 总净重: %s", order.net_weight)

        # ========== 5) 总毛重 ==========
        m = re.search(r"总毛重[:：]\s*([0-9]+(?:\.[0-9]+)?)\s*(?:KG|kg)?", text)
        if m:
            try:
                order.gross_weight = float(m.group(1))
            except Exception:
                order.gross_weight = None
        logger.info("[ABCParser] 总毛重: %s", order.gross_weight)

        # ========== 6) 产品编号统计（精确匹配 ABC 开头 + 数字） ==========
        # 规则：以 ABC 开头，后面必须紧跟数字，然后是任意字母/数字/-//
        # 正确示例：ABC2377-805/A/18K-C, ABC60598/16K-C4
        product_pattern = r"ABC\d[\w/-]*"
        
        # 匹配所有候选
        all_matches = re.findall(product_pattern, text)
        
        # 过滤掉无效匹配
        valid_products = []
        for code in all_matches:
            # 排除包含"公司"、"联系"等中文的
            if '公司' in code or '联系' in code:
                continue
            # 排除 ABC-后跟字母数字混合但不符合产品格式的
            if re.search(r"ABC-[A-Za-z]", code):
                if re.search(r"ABC-\d+[A-Za-z]", code):
                    continue
            # 确保编码长度合理（至少8位）
            if len(code) >= 8:
                valid_products.append(code)
        
        # 去重并保持顺序
        unique_products = []
        for code in valid_products:
            if code not in unique_products:
                unique_products.append(code)
        
        order.detail_count = len(unique_products)
        
        # ========== 详细日志输出 ==========
        logger.info("[ABCParser] ========== 解析结果汇总 ==========")
        logger.info("[ABCParser] 订单号: %s", order.order_no)
        logger.info("[ABCParser] 发货单号: %s", order.delivery_no)
        logger.info("[ABCParser] 收货地址: %s", order.receiver_address)
        logger.info("[ABCParser] 收货人: %s", order.receiver_name)
        logger.info("[ABCParser] 联系电话: %s", order.phone)
        logger.info("[ABCParser] 总净重: %s", order.net_weight)
        logger.info("[ABCParser] 总毛重: %s", order.gross_weight)
        logger.info("[ABCParser] 产品编码列表: %s", unique_products)
        logger.info("[ABCParser] 产品编码数量: %d", order.detail_count)
        logger.info("[ABCParser] ====================================")

        return order


__all__ = ["ABCParser", "BaseParser"]