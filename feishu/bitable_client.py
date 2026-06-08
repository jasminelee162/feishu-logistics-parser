"""
飞书多维表（Bitable）客户端。

类 `FeishuBitableClient` 提供方法：
    - get_access_token()
    - create_order_record()
    - create_address_record()
    - create_summary_record()

当前实现仅打印日志，不发出真实网络请求，方便本地联调。
"""
from typing import Any, Dict, Optional
from config.settings import SETTINGS
import logging

logger = logging.getLogger(__name__)


class FeishuBitableClient:
    """飞书多维表客户端。

    初始化时读取 `config.settings` 中的配置作为占位参数。
    """

    def __init__(self, api_key: str = "", app_id: str = None, app_secret: str = None, token: str = None):
        """初始化客户端。
        
        参数:
            api_key: API 密钥（兼容旧版）
            app_id: 飞书应用的 App ID
            app_secret: 飞书应用的 App Secret
            token: APP_TOKEN（多维表的 token）
        """
        self.app_id = app_id or SETTINGS.get("APP_ID")
        self.app_secret = app_secret or SETTINGS.get("APP_SECRET")
        self.token = token or SETTINGS.get("APP_TOKEN") or api_key
        # 表 id
        self.order_table_id = SETTINGS.get("ORDER_TABLE_ID")
        self.address_table_id = SETTINGS.get("ADDRESS_TABLE_ID")
        self.summary_table_id = SETTINGS.get("SUMMARY_TABLE_ID")

    def get_access_token(self) -> str:
        """占位：获取 access token（不实际调用），返回配置中的 token 或空字符串。"""
        logger.info("获取飞书 access token（占位），不会发起网络请求")
        return self.token or ""

    def create_order_record(self, order_data: Any) -> None:
        """在订单表创建记录（当前为占位实现，仅打印）。
        
        参数:
            order_data: 可以是 Order 对象或字典
        """
        # 兼容两种传入类型：Order 对象 或 字典
        if hasattr(order_data, 'file_name'):
            # 是 Order 对象（dataclass）
            file_name = order_data.file_name
            # 如果是对象且需要转为字典，可以在这里添加转换逻辑
            if hasattr(order_data, 'to_dict'):
                data_dict = order_data.to_dict()
            else:
                # 简单转换 dataclass 到 dict
                data_dict = {
                    'file_name': order_data.file_name,
                    'order_type': order_data.order_type,
                    'order_no': order_data.order_no,
                    'delivery_no': order_data.delivery_no,
                    'receiver_address': order_data.receiver_address,
                    'receiver_name': order_data.receiver_name,
                    'phone': order_data.phone,
                    'total_quantity': order_data.total_quantity,
                    'net_weight': order_data.net_weight,
                    'gross_weight': order_data.gross_weight,
                    'detail_count': order_data.detail_count,
                    'validation_status': order_data.validation_status,
                    'remark': order_data.remark,
                }
        else:
            # 是字典
            data_dict = order_data
            file_name = order_data.get('file_name') if isinstance(order_data, dict) else None
        
        logger.info(f"[FeishuBitableClient] create_order_record called. table={self.order_table_id}, file_name={file_name}")
        logger.debug(f"[FeishuBitableClient] 订单数据: {data_dict}")

    def create_address_record(self, address_data: Any) -> None:
        """在地址表创建记录（占位，仅打印）。"""
        if hasattr(address_data, 'file_name'):
            file_name = address_data.file_name
        elif isinstance(address_data, dict):
            file_name = address_data.get('file_name')
        else:
            file_name = None
        
        logger.info(f"[FeishuBitableClient] create_address_record called. table={self.address_table_id}, file_name={file_name}")

    def create_summary_record(self, summary_data: Any) -> None:
        """在汇总表创建记录（占位，仅打印）。"""
        if hasattr(summary_data, 'file_name'):
            file_name = summary_data.file_name
        elif isinstance(summary_data, dict):
            file_name = summary_data.get('file_name')
        else:
            file_name = None
        
        logger.info(f"[FeishuBitableClient] create_summary_record called. table={self.summary_table_id}, file_name={file_name}")


__all__ = ["FeishuBitableClient"]