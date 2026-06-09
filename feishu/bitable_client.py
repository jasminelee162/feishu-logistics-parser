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
        self.unknown_table_id = SETTINGS.get("UNKNOWN_TABLE_ID")

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

        # Make a shallow copy so we can retry with removed fields if necessary
        fields_to_send = dict(fields)

        # Debug: log the target table and payload (helps verify writes)
        try:
            logger.info("Preparing to write to table %s: %s", table_id, {k: (v if k != '原始文本' else '[trimmed]') for k, v in fields_to_send.items()})
        except Exception:
            # Ensure logging never raises
            pass

        # Try to create record, and if Feishu complains about unknown field names,
        # strip those fields and retry once.
        for attempt in range(2):
            body = {"fields": fields_to_send}

            resp = requests.post(url, json=body, headers=headers, timeout=10)
            data = resp.json()

            if data.get("code") == 0:
                # Ensure record_id exists and is usable; otherwise treat as error
                rec = (data.get("data") or {}).get("record") or {}
                record_id = rec.get("record_id")
                if record_id:
                    return record_id
                # If Feishu reports success but no record_id, treat as error
                raise Exception(f"Feishu returned success but missing record_id: {data}")

            # If Feishu reports FieldNameNotFound (1254045), try to parse the missing
            # field names from the error message, remove them, and retry once.
            err = data.get("error") or {}
            msg = err.get("message", "") or data.get("msg", "")

            # Detect pattern like: "Invalid request parameter: 'fields.校验状态'."
            if data.get("code") == 1254045 and isinstance(msg, str):
                missing = re.findall(r"'fields\.([^']+)'", msg)
                if missing:
                    for f in missing:
                        if f in fields_to_send:
                            logger.warning("Feishu field not found in table '%s': %s. Removing and retrying.", table_id, f)
                            fields_to_send.pop(f, None)
                    # If we've removed fields, continue to retry (next loop iteration)
                    continue

            # If we reach here, it's an unrecoverable error - raise with full response
            raise Exception(f"Feishu error: {data}")

    # =========================
    # 3. Order
    # =========================
    def create_order_record(self, order: Any, recognition_status: str = "成功") -> str:
        fields = {
            "文件名": getattr(order, "file_name", ""),
            "订单类型": getattr(order, "order_type", ""),
            "订单编号": getattr(order, "order_no", ""),
            "发货单号": getattr(order, "delivery_no", ""),
            "识别状态": recognition_status,
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
        # 明细行数：按 parser/validator 填充的 `order.detail_count` 写入（若存在）
        # Parser（如 ABC/XYZ）和 Validator 已经负责计算并填充该字段。
        if dc is not None:
            fields["明细行数"] = dc

        # The fields `校验状态` / `数量校验结果` / `综合校验状态` were removed
        # from the destination table. Do not write them anymore.

        # Link
        fields["关联订单ID"] = [order_record_id]

        # 如果在配置中指定了 SUMMARY_ALLOWED_FIELDS（逗号分割的字段名列表），
        # 则仅发送配置中允许的字段（同时始终允许 `关联订单ID`）。
        allowed = SETTINGS.get("SUMMARY_ALLOWED_FIELDS") or ""
        if isinstance(allowed, str) and allowed.strip():
            allowed_set = {s.strip() for s in allowed.split(",") if s.strip()}
            # 始终允许关联字段
            allowed_set.add("关联订单ID")
            # 过滤 fields
            fields = {k: v for k, v in fields.items() if k in allowed_set}

        return self.create_record(self.summary_table_id, fields)

    # =========================
    # Unknown order handling
    # =========================
    def create_unknown_record(self, order: Any, original_text: str = None, order_record_id: str = None) -> str:
        """当解析结果为 UNKNOWN 时，写入单独的 UNKNOWN 表以供人工复核。

        会写入字段：
        - `文件名`
        - `原始文本`（完整 PDF 文本，可能很长）
        - `状态`（使用 order.validation_status）
        - `记录时间`（当前时间的 unix 毫秒）
        - `关联订单ID`（Link 字段，array[str]，如果提供）
        - 以及 `校验标记`、`备注` 等可选字段
        """

        # 构造 UNKNOWN 表所需的字段，严格对应表头：记录ID, 文件名, 原始文本, 状态, 记录时间, 关联订单ID
        fields = {}
        if order_record_id:
            # 记录ID 作为文本字段，用于快速检索
            fields["记录ID"] = order_record_id
            # 关联订单ID 作为 Link 字段（数组）
            fields["关联订单ID"] = [order_record_id]

        fields["文件名"] = getattr(order, "file_name", "")
        fields["原始文本"] = original_text
        # 状态：优先使用识别的 validation_status，否则使用默认的需人工复合
        fields["状态"] = getattr(order, "validation_status", "需人工复合") or "需人工复合"
        # 记录时间：使用当前时间（毫秒）或 order.recognition_time
        fields["记录时间"] = self._to_unix_timestamp(getattr(order, "recognition_time", None))

        # 清理空值（保留空列表以便写入到飞书的多选/数组字段）
        fields = {k: v for k, v in fields.items() if v not in ("", None)}

        if not self.unknown_table_id:
            raise Exception("UNKNOWN_TABLE_ID is not configured in SETTINGS")

        # 尝试写入飞书 UNKNOWN 表，若失败则回退到本地文件保存以便人工复核
        try:
            return self.create_record(self.unknown_table_id, fields)
        except Exception as exc:
            try:
                # 将 payload 保存到 output/errors
                from pathlib import Path
                import json, time

                out_dir = Path("output/errors")
                out_dir.mkdir(parents=True, exist_ok=True)
                safe_name = (getattr(order, "file_name", "unknown") or "unknown").replace(".", "_")
                ts = int(time.time() * 1000)
                fn = out_dir / f"unknown_{safe_name}_{ts}.json"
                with fn.open("w", encoding="utf-8") as fh:
                    json.dump({"table_id": self.unknown_table_id, "fields": fields, "error": str(exc)}, fh, ensure_ascii=False, indent=2)
                logger.warning("写入 UNKNOWN 表失败，已保存到本地: %s", str(fn))
                return f"local:{str(fn)}"
            except Exception:
                # 最后兜底：抛出原始异常
                raise

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
        # 如果订单类型是 UNKNOWN，则仅写入 UNKNOWN 表，避免写入其它表格
        order_type = (getattr(order, "order_type", "") or "").upper()
        if order_type == "UNKNOWN":
            unknown_id = self.create_unknown_record(order)
            return {"unknown_record_id": unknown_id}

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