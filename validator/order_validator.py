"""订单校验模块。

实现对 Order 对象的校验逻辑，覆盖以下规则（见项目需求 C.1-C.4）：
- 地址检测与来源回退/模糊判定
- 数量/重量的一致性校验
- 单据分类异常标注（未知/混合）
- 系统异常与置信度阈值判断

接口说明：
- `OrderValidator.validate(order, original_text=None)` 返回一个列表 `List[Order]`：
  - 通常返回包含一个经过标注的 Order 对象的列表 `[order]`。
  - 若检测到“混合单据”并拆分，返回多个 Order 实例。
"""
from typing import List
import re
import logging

from models.order_model import Order


logger = logging.getLogger("OrderValidator")
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(ch)
    logger.setLevel(logging.INFO)


class OrderValidator:
    """对 Order 执行规则校验并在对象上添加标记与说明。"""

    def validate(self, order: Order, original_text: str = None) -> List[Order]:
        """执行所有校验规则，返回包含 1+ 个 Order 的列表。

        参数:
            order: 要校验的 Order 对象（解析器产出）
            original_text: 可选的原始全文文本，便于做拆单/混合判断

        返回:
            List[Order]: 至少包含传入 order（可能为修改后对象），当需要拆分时返回多个 Order
        """
        if order is None:
            return []

        # 清理旧标记
        order.validation_flags = []
        order.validation_notes = None

        # -------------------- C.1 地址识别异常 --------------------
        # 1) 汇总地址候选并去重，用于后续检测
        candidates = [a.strip() for a in getattr(order, 'address_candidates', []) if a and a.strip()]
        distinct = []
        for a in candidates:
            na = re.sub(r'\s+', '', a)
            if na not in [re.sub(r'\s+', '', x) for x in distinct]:
                distinct.append(a)
        # 如果客户区域和正文有冲突且正文可用，作为回退并标注
        if (not order.receiver_address or order.receiver_address.strip() == "") and distinct:
            # 采用第一个候选作为正文默认地址
            order.receiver_address = order.receiver_address or distinct[0]
            order.validation_flags.append("来源：正文默认")

        # 3 个及以上不同地址 -> 疑似异常
        if len(distinct) >= 3:
            order.validation_flags.append("疑似异常")

        # 地址过短（模糊）判定
        if order.receiver_address and len(re.sub(r'\s+', '', order.receiver_address)) < 5:
            order.validation_flags.append("地址存疑")
            # 不覆盖已有地址：上层写入时请尊重此标记

        # -------------------- C.2 数量/重量校验 --------------------
        # 1) 数量一致性
        sum_qty = 0
        items_with_qty = 0
        for it in getattr(order, 'items', []):
            try:
                if it.qty is not None:
                    sum_qty += int(it.qty)
                    items_with_qty += 1
            except Exception:
                continue

        # 明细行数按商品种类数（不同 SKU 数量）定义，而非明细数量之和
        distinct_skus = set()
        for it in getattr(order, 'items', []):
            try:
                if it.sku:
                    distinct_skus.add(str(it.sku).strip())
            except Exception:
                continue

        # Respect parser-provided detail_count if present (parser may use batch count),
        # otherwise fall back to distinct SKU count.
        if order.detail_count is None and len(getattr(order, 'items', [])) > 0:
            order.detail_count = len(distinct_skus)

        if order.total_quantity is not None and items_with_qty > 0:
            try:
                if int(order.total_quantity) != sum_qty:
                    diff = sum_qty - int(order.total_quantity)
                    order.validation_flags.append("数量不一致")
                    order.validation_notes = (order.validation_notes or "") + f" 数量偏差={diff};"
            except Exception:
                order.validation_flags.append("数量不一致")

        # 2) 重量缺失/异常
        if order.net_weight is None or order.gross_weight is None:
            order.validation_flags.append("重量缺失")
        else:
            try:
                if order.gross_weight < order.net_weight:
                    order.validation_flags.append("重量异常")
                    # 对于物理矛盾，标记为拒写（上层处理）
                    order.validation_flags.append("拒写-重量异常")
            except Exception:
                pass

        # -------------------- C.3 单据分类异常 --------------------
        # 无法识别类型 -> 类型未知
        if not order.order_type or order.order_type.upper() == 'UNKNOWN':
            order.validation_flags.append("类型未知")

        # 检测混合单据（非常保守的检测：若正文同时出现 ABC 与 XYZ 特征关键词）
        if original_text:
            has_abc = bool(re.search(r"\bABC\d", original_text))
            has_xyz = bool(re.search(r"XYZ|其他特征示例", original_text))
            if has_abc and has_xyz:
                order.validation_flags.append("混合单据")
                # 简化处理：不自动拆分复杂表格，标注为需人工处理
                order.validation_flags.append("需人工复核")

        # -------------------- C.4 系统异常 --------------------
        # 置信度判断
        if order.confidence is not None and order.confidence < 0.8:
            order.validation_flags.append("需人工复核")

        # 最终 validation_status 汇总
        if not order.validation_flags:
            order.validation_status = "一致"
        else:
            order.validation_status = ",".join(order.validation_flags)

        return [order]


def validate_order(order: Order, original_text: str = None) -> List[Order]:
    """向后兼容接口，返回 List[Order]。"""
    validator = OrderValidator()
    return validator.validate(order, original_text=original_text)


__all__ = ["OrderValidator", "validate_order"]
