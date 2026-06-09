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
from validator.order_validator import OrderValidator, validate_order
from feishu.bitable_client import FeishuBitableClient
from models.order_model import Order
from dataclasses import asdict
import json
from pathlib import Path


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

    # 校验（validator 返回 List[Order]，以支持拆分或多结果）
    validator = OrderValidator()
    validated_orders = validator.validate(order, original_text=text)

    # 调用飞书客户端
    feishu = FeishuBitableClient()

    # 输出目录（用于保存被拒写的异常记录）
    errs_dir = Path("output/errors")
    errs_dir.mkdir(parents=True, exist_ok=True)

    import uuid

    for idx, ord_obj in enumerate(validated_orders):
        print("解析并校验后的订单: ")
        print(asdict(ord_obj))

        flags = ord_obj.validation_flags or []
        # 若检测到拒写标记（如重量物理矛盾），则不写入飞书并保存到本地供人工处理
        if any(f.startswith("拒写") for f in flags):
            print(f"订单被拒写，原因: {flags}")
            outp = errs_dir / f"{p.stem}_rejected_{idx}.json"
            with outp.open("w", encoding="utf-8") as fh:
                json.dump(asdict(ord_obj), fh, ensure_ascii=False, indent=2)
            continue

        # 若需要人工复核或疑似异常，仍写入订单表，但打印提醒并在备注中保留标记
        if any(f in ("需人工复核", "疑似异常", "类型未知") for f in flags):
            ord_obj.remark = (ord_obj.remark or "") + " [自动标记：" + ",".join(flags) + "]"
            print(f"注意：订单需人工复核或为疑似异常，标记={flags}")
        # 若订单为 UNKNOWN（或被标记为类型未知），只写入 UNKNOWN 表并跳过其他表
        is_unknown = (getattr(ord_obj, "order_type", "") or "").upper() == "UNKNOWN" or any(f == "类型未知" for f in flags)
        if is_unknown:
            # 首先在 ORDER_TABLE 写入一条识别为需人工复合的订单记录
            try:
                order_record_id = feishu.create_order_record(ord_obj, recognition_status="需人工复合")
                print(f"飞书订单记录创建成功 (需人工复合): {order_record_id}")
            except Exception as exc:
                # 若写入订单表失败，则生成一个本地关联 ID，继续写 UNKNOWN 表并保存回退
                import time
                order_record_id = f"local:{p.stem}:{idx}:{int(time.time()*1000)}"
                print(f"写入订单表失败，使用本地关联ID: {order_record_id}, 错误: {exc}")

            # 然后在 UNKNOWN 表中写入完整记录并关联到 order_record_id
            try:
                unknown_id = feishu.create_unknown_record(ord_obj, original_text=text, order_record_id=order_record_id)
                print(f"飞书未知订单记录创建成功: {unknown_id}")
            except Exception as exc:
                print(f"写入未知表失败: {exc}")
            continue

        # 正常写入飞书（非 UNKNOWN）
        order_record_id = feishu.create_order_record(ord_obj)
        if order_record_id:
            print(f"飞书订单记录创建成功: {order_record_id}")
            addr_record_id = feishu.create_address_record(ord_obj, order_record_id)
            if addr_record_id:
                print(f"飞书地址记录创建成功: {addr_record_id}")
            summary_record_id = feishu.create_summary_record(ord_obj, order_record_id)
            if summary_record_id:
                print(f"飞书汇总记录创建成功: {summary_record_id}")

    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python app.py <path-to-pdf>")
        sys.exit(1)
    code = main(sys.argv[1])
    sys.exit(code)