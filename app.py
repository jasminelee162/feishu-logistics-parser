"""
主运行入口：实现 PDF -> 分类 -> 解析 -> 校验 -> 打印 的完整主流程。

使用说明：
    python app.py <path-to-pdf>

注：当前解析器为占位实现，仅返回空的 Order 对象，校验默认通过（"一致").
"""
import sys
from pathlib import Path
from pdf.pdf_reader import PDFReader
from parser.classifier import OrderClassifier
from parser.abc_parser import ABCParser
from parser.xyz_parser import XYZParser
from validator.order_validator import OrderValidator
from feishu.bitable_client import FeishuBitableClient
from models.order_model import Order
from dataclasses import asdict


def main(pdf_path: str) -> int:
    """按流程处理单个 PDF 文件并打印处理结果。

    返回值: 0 表示成功，非 0 表示错误。
    """
    p = Path(pdf_path)
    if not p.exists():
        print(f"PDF 文件未找到: {pdf_path}")
        return 2

    # 读取 PDF
    reader = PDFReader()
    try:
        text = reader.read_pdf(str(p))
    except Exception as exc:
        print(f"读取 PDF 失败: {exc}")
        return 3

    # ========== 添加调试代码：打印PDF原始文本 ==========
    print("\n" + "=" * 50)
    print("PDF文本开始")
    print("=" * 50)
    print(text[:3000])  # 打印前3000字符
    print("=" * 50)
    print("PDF文本结束")
    print("=" * 50 + "\n")
    # ========== 调试代码结束 ==========

    # 分类
    classifier = OrderClassifier()
    order_type = classifier.classify(text)
    print(f"检测到订单类型: {order_type}")

    # 解析
    order: Order
    if order_type == "ABC":
        parser = ABCParser()
        order = parser.parse(text, file_name=p.name)
    elif order_type == "XYZ":
        parser = XYZParser()
        order = parser.parse(text, file_name=p.name)
    else:
        # 未知类型，构造基础 Order 并返回
        order = Order(file_name=p.name, order_type="UNKNOWN")

    # 校验
    validator = OrderValidator()
    order = validator.validate(order)

    # 打印结果（可替换为写入飞书多维表）
    print("解析并校验后的订单: ")
    print(asdict(order))

    # 调用占位的飞书客户端（仅打印）
    feishu = FeishuBitableClient()
    feishu.create_order_record(order.to_dict() if hasattr(order, 'to_dict') else asdict(order))

    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python app.py <path-to-pdf>")
        sys.exit(1)
    code = main(sys.argv[1])
    sys.exit(code)