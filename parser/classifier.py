"""
PDF 订单分类器模块。

提供类 `OrderClassifier`，用于根据文本内容判断订单类型：
    - 包含 "Delivery Docket" 返回 "ABC"
    - 包含 "送货通知单" 或 "Delivery Notice" 返回 "XYZ"
    - 否则返回 "UNKNOWN"
所有注释使用中文说明。
"""


class OrderClassifier:
    """基于文本关键字的简单订单分类器（面向对象设计）。"""

    def classify(self, text: str) -> str:
        """对提供的文本进行分类并返回类型字符串。

        参数:
            text: PDF 提取的全文字符串

        返回:
            'ABC', 'XYZ' 或 'UNKNOWN'
        """
        if not text:
            return "UNKNOWN"
        lowered = text
        # 精确匹配英文/中文关键字
        if "Delivery Docket" in text:
            return "ABC"
        if "送货通知单" in text or "Delivery Notice" in text:
            return "XYZ"
        return "UNKNOWN"


def classify_pdf(text: str) -> str:
    """向后兼容的函数接口，直接使用 `OrderClassifier` 实例完成分类。"""
    return OrderClassifier().classify(text)
"""订单分类器模块

根据 PDF 提取的文本判断订单类型：ABC / XYZ / UNKNOWN
"""


class OrderClassifier:
    """订单分类器。

    规则：
    - 文本包含 "Delivery Docket"（不区分大小写） -> 返回 "ABC"
    - 文本包含 "送货通知单" 或 "Delivery Notice" -> 返回 "XYZ"
    - 否则返回 "UNKNOWN"
    """

    def classify(self, text: str) -> str:
        if not text:
            return "UNKNOWN"
        up = text.upper()
        if "DELIVERY DOCKET" in up:
            return "ABC"
        # 检查中文或英文关键字
        if "送货通知单" in text or "DELIVERY NOTICE" in up:
            return "XYZ"
        return "UNKNOWN"
