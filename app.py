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
from parser.text_block_builder import TextBlockBuilder
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
    # 语义块恢复：在 Parser 之前修复地址/姓名等断裂问题
    block_builder = TextBlockBuilder()
    rebuilt = block_builder.build(text)
    # 仅在调试时打印处理后片段（便于验证），这里保留有限输出
    print("\n---- TextBlockBuilder: 处理后片段 (前3000字符) ----")
    print(rebuilt[:3000])
    text = rebuilt

    # 分类（在文本恢复后进行）
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

    # 调用飞书客户端，传入 Order 对象（不转换为 dict）
    feishu = FeishuBitableClient()
    order_record_id = feishu.create_order_record(order)
    if order_record_id:
        print(f"飞书订单记录创建成功: {order_record_id}")
    # 创建地址和汇总记录，分别与订单记录关联
    addr_record_id = feishu.create_address_record(order, order_record_id)

    if addr_record_id:
        print(f"飞书地址记录创建成功: {addr_record_id}")
    summary_record_id = feishu.create_summary_record(order, order_record_id)
    if summary_record_id:
        print(f"飞书汇总记录创建成功: {summary_record_id}")

    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python app.py <path-to-pdf>")
        sys.exit(1)
    code = main(sys.argv[1])
    sys.exit(code)