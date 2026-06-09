from typing import Any, Dict, Optional
import logging
import time
import requests

from config.settings import SETTINGS

logger = logging.getLogger("FeishuBitableClient")


class FeishuBitableClient:
    """
    工业级飞书多维表客户端（稳定版）

    设计原则：
    1. 无状态（不依赖 self._last_xxx）
    2. record_id 作为唯一关联ID
    3. Link字段统一数组[str]
    4. 所有关联必须显式传递
    """

    AUTH_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    RECORD_URL = "https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"

    def __init__(self, app_id=None, app_secret=None, app_token=None):
        self.app_id = app_id or SETTINGS.get("APP_ID")
        self.app_secret = app_secret or SETTINGS.get("APP_SECRET")
        self.app_token = app_token or SETTINGS.get("APP_TOKEN")

        self.order_table_id = SETTINGS.get("ORDER_TABLE_ID")
        self.address_table_id = SETTINGS.get("ADDRESS_TABLE_ID")
        self.summary_table_id = SETTINGS.get("SUMMARY_TABLE_ID")

        self._token = None
        self._expire = 0

    # =========================
    # 1. Token
    # =========================
    def get_token(self):
        now = time.time()
        if self._token and now < self._expire - 30:
            return self._token

        resp = requests.post(
            self.AUTH_URL,
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=10
        )
        data = resp.json()

        if data.get("tenant_access_token"):
            self._token = data["tenant_access_token"]
            self._expire = now + int(data.get("expire", 3600))
            return self._token

        raise Exception(f"token error: {data}")

    # =========================
    # 2. 通用写入
    # =========================
    def create_record(self, table_id: str, fields: Dict[str, Any]) -> str:
        url = self.RECORD_URL.format(
            app_token=self.app_token,
            table_id=table_id
        )

        headers = {
            "Authorization": f"Bearer {self.get_token()}",
            "Content-Type": "application/json"
        }

        body = {"fields": fields}

        resp = requests.post(url, json=body, headers=headers, timeout=10)
        data = resp.json()

        if data.get("code") != 0:
            raise Exception(f"Feishu error: {data}")

        record_id = data["data"]["record"]["record_id"]
        return record_id

    # =========================
    # 3. Order
    # =========================
    def create_order_record(self, order: Any) -> str:
        fields = {
            "文件名": getattr(order, "file_name", ""),
            "订单类型": getattr(order, "order_type", ""),
            "订单编号": getattr(order, "order_no", ""),
            "发货单号": getattr(order, "delivery_no", ""),
            "识别状态": "成功",
            "备注": getattr(order, "remark", "")
        }

        # 清理空值
        fields = {k: v for k, v in fields.items() if v not in ("", None)}

        return self.create_record(self.order_table_id, fields)

    # =========================
    # 4. Address（关键：Link）
    # =========================
    def create_address_record(self, order: Any, order_record_id: str) -> str:
        fields = {
            "发货地": getattr(order, "sender_address", ""),
            "收货地址": getattr(order, "receiver_address", ""),
            "收货人": getattr(order, "receiver_name", ""),
            "联系电话": getattr(order, "phone", ""),
            "地址来源": self._parse_source(order)
        }

        fields = {k: v for k, v in fields.items() if v not in ("", None)}

        # ✅ 正确 Link 写法（核心）
        fields["关联订单ID"] = [order_record_id]

        return self.create_record(self.address_table_id, fields)

    # =========================
    # 5. Summary（同样 Link）
    # =========================
    def create_summary_record(self, order: Any, order_record_id: str) -> str:
        fields = {
            "总数量": getattr(order, "total_quantity", 0),
            "总净重": getattr(order, "net_weight", 0),
            "总毛重": getattr(order, "gross_weight", 0),
            "明细行数": getattr(order, "detail_count", 0),
            "校验状态": getattr(order, "validation_status", "一致")
        }

        # Link
        fields["关联订单ID"] = [order_record_id]

        return self.create_record(self.summary_table_id, fields)

    # =========================
    # 6. 一键流水（工业级核心）
    # =========================
    def process_order(self, order: Any) -> Dict[str, str]:
        """
        完整流水：
        Order -> Address -> Summary
        """
        order_id = self.create_order_record(order)

        address_id = self.create_address_record(order, order_id)
        summary_id = self.create_summary_record(order, order_id)

        return {
            "order_record_id": order_id,
            "address_record_id": address_id,
            "summary_record_id": summary_id
        }

    # =========================
    # 7. 工具
    # =========================
    def _parse_source(self, order: Any) -> str:
        remark = getattr(order, "remark", "") or ""

        for k in ["客户要求", "发货信息", "正文默认", "右上角"]:
            if k in remark:
                return k

        return "正文默认"