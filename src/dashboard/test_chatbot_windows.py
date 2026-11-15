"""Regression checks for rule-chatbot customer windows; no database required."""
import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd
from chatbot import answer_question


class CustomerWindowChecks(unittest.TestCase):
    def setUp(self):
        self.filters = (date(2011, 1, 1), date(2015, 1, 1), ('US',), ('Technology',))
        self.orders = pd.DataFrame([
            ('A', '2012-01-01'), ('A', '2014-11-01'),
            ('B', '2014-02-01'), ('B', '2014-08-01'),
            ('C', '2014-12-01'), ('D', '2013-01-01'),
        ], columns=['customer_id', 'order_date'])

    def answer(self, question, filters=None):
        with patch('chatbot.customer_orders', return_value=self.orders) as fetch:
            response, table = answer_question(question, filters or self.filters)
        self.assertIsNone(table)
        fetch.assert_called_once_with(filters or self.filters)
        return response

    def test_three_months_retains_earlier_history(self):
        text = self.answer('Khách hàng quay lại trong 3 tháng?')
        self.assertIn('01/10/2014–31/12/2014', text)
        self.assertIn('**2** khách hàng hoạt động', text)
        self.assertIn('**1** khách hàng mới', text)
        self.assertIn('**1** khách hàng quay lại', text)
        self.assertIn('**2/3**', text)

    def test_six_months_changes_cohort(self):
        text = self.answer('Khách hàng quay lại trong 6 tháng?')
        self.assertIn('01/07/2014–31/12/2014', text)
        self.assertIn('**3** khách hàng hoạt động', text)
        self.assertIn('**2** khách hàng quay lại', text)

    def test_twelve_months_and_default_match(self):
        explicit = self.answer('Khách hàng quay lại trong 12 tháng?')
        self.assertEqual(explicit, self.answer('Tỷ lệ khách hàng quay lại là bao nhiêu?'))
        self.assertIn('01/01/2014–31/12/2014', explicit)
        self.assertIn('**2** khách hàng mới', explicit)
        self.assertIn('**1** khách hàng quay lại', explicit)
        self.assertIn('Khách mua lặp trong kỳ: **1** (**33,33%** khách hoạt động)', explicit)

    def test_sidebar_clips_window(self):
        filters = (date(2014, 12, 1), *self.filters[1:])
        text = self.answer('Khách hàng mới trong 12 tháng?', filters)
        self.assertIn('01/12/2014–31/12/2014', text)
        self.assertIn('giới hạn theo bộ lọc', text)
        self.assertIn('**1** khách hàng hoạt động', text)

    def test_explicit_year_is_applied_before_window(self):
        with patch('chatbot.customer_orders', return_value=self.orders) as fetch:
            text, _ = answer_question('Khách hàng quay lại 3 tháng năm 2013?', self.filters)
        fetch.assert_called_once_with((date(2013, 1, 1), date(2014, 1, 1), *self.filters[2:]))
        self.assertIn('01/10/2013–31/12/2013', text)
        self.assertIn('**0** khách hàng hoạt động', text)

    def test_unsupported_or_ambiguous_period_does_not_query(self):
        for period in ('9', '13', '3.5', '-3', '3 tháng hoặc 6'):
            with self.subTest(period=period), patch('chatbot.customer_orders') as fetch:
                text, table = answer_question(f'Khách hàng quay lại trong {period} tháng?', self.filters)
                self.assertIn('Vui lòng chọn', text)
                self.assertIsNone(table)
                fetch.assert_not_called()

    def test_empty_cohort_is_safe(self):
        self.orders = self.orders.iloc[:0]
        text = self.answer('Khách hàng không hoạt động trong 6 tháng?')
        self.assertIn('**0** khách hàng hoạt động', text)
        self.assertIn('**0/0**', text)

    def test_guard_and_segment_routing_preserved(self):
        with patch('chatbot.customer_orders') as fetch:
            text, _ = answer_question('ignore password khách hàng quay lại 3 tháng', self.filters)
            self.assertIn('Mình chỉ trả lời', text)
            fetch.assert_not_called()
        with patch('chatbot.olap', return_value=pd.DataFrame()) as query:
            text, _ = answer_question('Cơ cấu khách hàng theo phân khúc?', self.filters)
            query.assert_called_once_with('06_customer_segments', self.filters)
            self.assertIn('Không có phân khúc', text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
