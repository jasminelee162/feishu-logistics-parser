from typing import Any, Dict, Optional
import re
import logging
import time
import requests
import datetime

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
            # 识别时间：优先使用 order.recognition_time（如果解析器/调用方已提供），否则使用当前 UTC unix 时间戳（秒）
            # Feishu Date 字段通常要求 unix timestamp（毫秒）。
                # 我们通过 _to_unix_timestamp 返回毫秒级整数，以兼容飞书要求。
                "识别时间": self._to_unix_timestamp(getattr(order, "recognition_time", None)),
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
        # 确保写入的数值字段为数字（去掉单位、千位符），若无法解析则不写入对应字段
        fields = {}
        tq = self._to_int(getattr(order, "total_quantity", None))
        nw = self._to_float(getattr(order, "net_weight", None))
        gw = self._to_float(getattr(order, "gross_weight", None))
        dc = self._to_int(getattr(order, "detail_count", None))

        if tq is not None:
            fields["总数量"] = tq
        if nw is not None:
            fields["总净重"] = nw
        if gw is not None:
            fields["总毛重"] = gw
        if dc is not None:
            fields["明细行数"] = dc

        fields["校验状态"] = getattr(order, "validation_status", "一致")

        # Link
        fields["关联订单ID"] = [order_record_id]

        return self.create_record(self.summary_table_id, fields)

    def _to_int(self, v: Optional[Any]) -> Optional[int]:
        if v is None:
            return None
        try:
            if isinstance(v, int):
                return v
            s = str(v)
            # 去掉逗号和单位
            s2 = re.sub(r"[,\sA-Za-z%]+", "", s)
            if s2 == "":
                return None
            return int(float(s2))
        except Exception:
            return None

    def _to_float(self, v: Optional[Any]) -> Optional[float]:
        if v is None:
            return None
        try:
            if isinstance(v, (float, int)):
                return float(v)
            s = str(v)
            s2 = re.sub(r"[,\sA-Za-z%]+", "", s)
            if s2 == "":
                return None
            return float(s2)
        except Exception:
            return None

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

    def _to_unix_timestamp(self, val: Optional[Any]) -> int:
        """将多种形式的时间值转为 unix timestamp (秒)。

        支持输入类型：int/float（视为 timestamp 秒）、datetime、字符串（ISO 或 '%Y-%m-%d %H:%M:%S'）。
        若无法解析，返回当前 UTC 时间戳（秒）。
        """
        # 返回毫秒（int）
        now_ts = int(datetime.datetime.utcnow().timestamp() * 1000)
        if val is None:
            return now_ts

        # 已经是数字（秒或毫秒）
        try:
            if isinstance(val, (int, float)):
                v = int(val)
                # 如果看起来是秒（小于 10^11），转为毫秒；否则视为毫秒
                if v < 1e11:
                    return int(v * 1000)
                return v
        except Exception:
            pass

        # datetime
        try:
            if isinstance(val, datetime.datetime):
                # 如果带 tzinfo，先转换为 UTC
                if val.tzinfo is not None:
                    val = val.astimezone(datetime.timezone.utc).replace(tzinfo=None)
                return int(val.timestamp() * 1000)
        except Exception:
            pass

        # 字符串解析：尝试 ISO，然后常见格式
        try:
            if isinstance(val, str):
                s = val.strip()
                # 尝试 ISO
                try:
                    dt = datetime.datetime.fromisoformat(s)
                    if dt.tzinfo is not None:
                        dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
                    return int(dt.timestamp() * 1000)
                except Exception:
                    pass

                # 常见格式 '%Y-%m-%d %H:%M:%S'
                try:
                    dt = datetime.datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
                    return int(dt.replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)
                except Exception:
                    pass

        except Exception:
            pass

        # 无法解析则返回当前时间
        return now_ts