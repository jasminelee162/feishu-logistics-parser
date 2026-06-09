"""
订单数据模型定义（使用 dataclass）。

包含统一的 `Order` 数据类，用于在解析、校验、存储各环节流转。
所有字段均使用明确类型，并提供默认值以方便占位。
"""
from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class OrderItem:
    """单条明细的简单模型（占位）。"""
    sku: Optional[str] = None
    qty: Optional[int] = None


@dataclass
class Order:
    """统一订单对象。

    字段:
        file_name: 原始文件名
        order_type: 订单类型，例如 'ABC' / 'XYZ' / 'UNKNOWN'
        order_no: 订单编号
        delivery_no: 送货单号
        sender_address: 发货地址
        receiver_address: 收货地址
        receiver_name: 收货人姓名
        phone: 联系电话
        total_quantity: 总数量
        net_weight: 净重
        gross_weight: 毛重
        detail_count: 明细行数
        validation_status: 校验结果（占位字符串）
        remark: 备注
    """

    file_name: Optional[str] = None
    order_type: str = "UNKNOWN"
    order_no: Optional[str] = None
    delivery_no: Optional[str] = None
    sender_address: Optional[str] = None
    receiver_address: Optional[str] = None
    receiver_name: Optional[str] = None
    phone: Optional[str] = None
    total_quantity: Optional[int] = None
    net_weight: Optional[float] = None
    gross_weight: Optional[float] = None
    # 发货日期（字符串，格式依赖源文件）
    ship_date: Optional[str] = None
    # 预计/预估抵达日期
    eta: Optional[str] = None
    detail_count: Optional[int] = None
    validation_status: Optional[str] = None
    remark: Optional[str] = None
    items: List[OrderItem] = field(default_factory=list)

    # 以下为校验/审计支持字段
    # 存放校验发现的标记，例如: '地址存疑','数量不一致','重量异常','需人工复核' 等
    validation_flags: List[str] = field(default_factory=list)
    # 更详细的校验说明（例如偏差值、缺失字段说明）
    validation_notes: Optional[str] = None
    # 解析阶段收集的地址候选列表（用于地址冲突检测）
    address_candidates: List[str] = field(default_factory=list)
    # 简单置信度评估（0.0 - 1.0），解析器可填写
    confidence: Optional[float] = None

    # 如果校验器需要产生拆分结果，可放在这里（可选，通常 validate 返回多个 Order）
    split_from: Optional[str] = None
    # 识别时间（可由外部在解析/调用时设置），格式为字符串或 datetime，最终写入飞书时会被转换为 unix timestamp
    recognition_time: Optional[str] = None

    def to_dict(self) -> dict:
        """返回可序列化字典（便于打印/存储）。"""
        return asdict(self)
