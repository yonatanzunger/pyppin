import io
import textwrap
import unittest

from pyppin.text.print_counter import PrintCounter


class PrintCounterTest(unittest.TestCase):
    def test_print_counter(self) -> None:
        output = io.StringIO()
        with PrintCounter(
            print_every_n=1000,
            print_every_time=None,
            format="Count: {count:si}; foo: {foo:.1si}",
            final_format="Final: {count}; foo: {foo}",
            stream=output,
        ) as counter:
            for i in range(5000):
                counter.inc(foo=i)

        self.assertEqual(
            textwrap.dedent(
                """\
                Count: 1000; foo: 499.5k
                Count: 2.0k; foo: 2.0M
                Count: 3.0k; foo: 4.5M
                Count: 4.0k; foo: 8.0M
                Count: 5.0k; foo: 12.5M
                Final: 5000; foo: 12497500
                """
            ),
            output.getvalue(),
        )
