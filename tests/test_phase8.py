"""Run with:  python -m unittest discover -s tests -v"""
import tempfile
import unittest
from datetime import time
from pathlib import Path

from bot import restore
from bot import backup
from bot.services import opsrules


class ParseTimeTests(unittest.TestCase):
    def test_good_and_bad(self):
        d = time(3, 0)
        self.assertEqual(opsrules.parse_hhmm("04:30", d), time(4, 30))
        self.assertEqual(opsrules.parse_hhmm("4.05", d), time(4, 5))
        self.assertEqual(opsrules.parse_hhmm(" 23:59 ", d), time(23, 59))
        for bad in ("24:00", "12:60", "abc", "", None, "3"):
            self.assertEqual(opsrules.parse_hhmm(bad, d), d)


class UptimeTests(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(opsrules.format_uptime(30), "0m")
        self.assertEqual(opsrules.format_uptime(95 * 60), "1h 35m")
        self.assertEqual(opsrules.format_uptime(2 * 86400 + 3 * 3600), "2d 3h")
        self.assertEqual(opsrules.format_uptime(-5), "0m")


class TableOrderTests(unittest.TestCase):
    def test_parents_come_first(self):
        tables = ["order_items", "orders", "users", "meals", "payments"]
        fks = [("orders", "users"), ("order_items", "orders"), ("order_items", "meals"), ("payments", "orders")]
        order = opsrules.order_tables(tables, fks)
        for child, parent in fks:
            self.assertLess(order.index(parent), order.index(child))
        self.assertEqual(sorted(order), sorted(tables))

    def test_self_reference_and_cycle_do_not_loop_forever(self):
        order = opsrules.order_tables(["a", "b", "c"], [("a", "a"), ("b", "c"), ("c", "b")])
        self.assertEqual(sorted(order), ["a", "b", "c"])
        self.assertEqual(order[0], "a")

    def test_unknown_tables_in_foreign_keys_are_ignored(self):
        self.assertEqual(opsrules.order_tables(["a"], [("a", "other_schema_table")]), ["a"])


class PruneTests(unittest.TestCase):
    NAMES = ["fitmeal-20261101-030000.sql", "fitmeal-20261102-030000.sql", "fitmeal-20261103-030000.sql",
             "notes.txt", "fitmeal-latest.sql"]

    def test_keeps_the_newest(self):
        self.assertEqual(opsrules.files_to_delete(self.NAMES, 2), ["fitmeal-20261101-030000.sql"])
        self.assertEqual(opsrules.files_to_delete(self.NAMES, 3), [])
        self.assertEqual(opsrules.files_to_delete(self.NAMES, 10), [])

    def test_never_touches_other_files(self):
        deleted = opsrules.files_to_delete(self.NAMES, 1)
        self.assertNotIn("notes.txt", deleted)
        self.assertNotIn("fitmeal-latest.sql", deleted)

    def test_latest_backup_finds_the_newest_file(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertIsNone(backup.latest_backup(Path(folder)))
            for name in ("fitmeal-20261101-030000.sql", "fitmeal-20261103-030000.sql", "other.sql"):
                (Path(folder) / name).write_text("x")
            self.assertEqual(backup.latest_backup(Path(folder)).name, "fitmeal-20261103-030000.sql")


class StrayTests(unittest.TestCase):
    def test_one_reply_a_minute(self):
        self.assertTrue(opsrules.stray_reply_allowed(None, 100.0))
        self.assertFalse(opsrules.stray_reply_allowed(100.0, 130.0))
        self.assertTrue(opsrules.stray_reply_allowed(100.0, 161.0))


class RestoreHeaderTests(unittest.TestCase):
    def test_header_check(self):
        self.assertTrue(restore.check_header(backup.HEADER + "\n-- Created: x\n"))
        self.assertFalse(restore.check_header("DROP DATABASE fitmeal;"))


if __name__ == "__main__":
    unittest.main()
