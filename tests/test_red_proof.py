import unittest


class RedProofTest(unittest.TestCase):
    """Deliberately failing: this delivery's pipeline MUST go red so the report path can be proven."""

    def test_deliberately_red(self):
        self.assertEqual(1, 2, 'red-proof: this test is designed to fail so the pipeline is red')


if __name__ == '__main__':
    unittest.main()
