import unittest

from models.order_model import Order, OrderItem
from validator.order_validator import OrderValidator


class TestOrderValidator(unittest.TestCase):
    def setUp(self):
        self.v = OrderValidator()

    def test_address_fallback_and_save_candidate(self):
        o = Order(file_name="a.pdf")
        o.address_candidates = ["北京市海淀区西二旗路1号", "北京市海淀区西二旗路1号"]
        res = self.v.validate(o)
        self.assertTrue(isinstance(res, list))
        out = res[0]
        self.assertIn("来源：正文默认", out.validation_flags)
        self.assertEqual(out.receiver_address, "北京市海淀区西二旗路1号")

    def test_short_address_flag(self):
        o = Order(file_name="b.pdf")
        o.address_candidates = ["京A1"]
        res = self.v.validate(o)
        out = res[0]
        self.assertIn("地址存疑", out.validation_flags)

    def test_quantity_inconsistency(self):
        o = Order(file_name="c.pdf")
        o.total_quantity = 5
        o.items = [OrderItem(qty=2), OrderItem(qty=1)]
        res = self.v.validate(o)
        out = res[0]
        self.assertIn("数量不一致", out.validation_flags)
        self.assertIsNotNone(out.validation_notes)

    def test_weight_missing_and_anomaly(self):
        # missing
        o = Order(file_name="d.pdf")
        o.net_weight = None
        o.gross_weight = None
        res = self.v.validate(o)
        out = res[0]
        self.assertIn("重量缺失", out.validation_flags)

        # anomaly
        o2 = Order(file_name="e.pdf")
        o2.net_weight = 10.0
        o2.gross_weight = 9.0
        res2 = self.v.validate(o2)
        out2 = res2[0]
        self.assertIn("重量异常", out2.validation_flags)
        self.assertIn("拒写", ",".join(out2.validation_flags))

    def test_confidence_flag(self):
        o = Order(file_name="f.pdf")
        o.confidence = 0.7
        res = self.v.validate(o)
        out = res[0]
        self.assertIn("需人工复核", out.validation_flags)


if __name__ == '__main__':
    unittest.main()
