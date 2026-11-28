"""Bir nechta backend worker'i: Redis kesh yiqilmasligi, tarjima qulfi jarayonlar o'rtasida, worker soni."""
import os
import runpy
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase

from . import translation
from .cache import SafeRedisCache

GUNICORN_CONF = Path(settings.BASE_DIR).parent / "deploy" / "gunicorn.conf.py"


class SafeRedisCacheTests(SimpleTestCase):
    def test_dead_redis_does_not_break_callers(self):
        c = SafeRedisCache("redis://127.0.0.1:1/0", {"OPTIONS": {"socket_connect_timeout": 0.3, "socket_timeout": 0.3}})
        self.assertEqual(c.get("k", 7), 7)
        self.assertIsNone(c.set("k", 1, 10))
        self.assertTrue(c.add("lock", 1, 10))  # qulf «olindi» — ish to'xtab qolmaydi
        self.assertFalse(c.delete("k"))
        self.assertEqual(c.get_many(["a", "b"]), {})
        self.assertEqual(c.incr("n", 2), 2)


class TranslationLockTests(SimpleTestCase):
    def setUp(self):
        for k in (translation._RUN_KEY, translation._AGAIN_KEY, translation._VER_KEY, translation._INFO_KEY):
            cache.delete(k)
        translation._state.update(running=True, again=False)

    def tearDown(self):
        translation._state.update(running=False, again=False)
        cache.delete(translation._RUN_KEY)
        cache.delete(translation._AGAIN_KEY)

    def test_other_process_holds_lock_then_runs_again(self):
        cache.set(translation._RUN_KEY, 99999, 60)  # boshqa worker tarjima qilyapti
        with mock.patch.object(translation, "translate_pending") as tp, \
                mock.patch.object(translation, "close_old_connections"):
            translation._worker()
        tp.assert_not_called()
        self.assertFalse(translation._state["running"])
        self.assertTrue(cache.get(translation._AGAIN_KEY))  # egasiga «yana aylan» belgisi qoldi

        # egasi: qulfni ochgach belgini ko'radi va yana bir marta aylanadi
        cache.delete(translation._RUN_KEY)
        translation._state["running"] = True
        calls = []

        def run():
            calls.append(1)
            if len(calls) == 1:
                cache.set(translation._AGAIN_KEY, 1, 60)  # aylanish paytida yana saqlash bo'ldi (boshqa worker)

        with mock.patch.object(translation, "translate_pending", side_effect=run), \
                mock.patch.object(translation, "close_old_connections"):
            translation._worker()
        self.assertEqual(len(calls), 2)
        self.assertIsNone(cache.get(translation._RUN_KEY))
        self.assertFalse(translation._state["running"])

    def test_version_is_shared(self):
        cache.set(translation._VER_KEY, 5, None)
        self.assertEqual(translation.version()[0], 5)


class GunicornWorkersTests(SimpleTestCase):
    def workers(self, **env):
        clean = {k: v for k, v in os.environ.items() if k not in ("ZONA_REDIS_URL", "ZONA_WEB_WORKERS")}
        with mock.patch.dict(os.environ, {**clean, **env}, clear=True):
            return runpy.run_path(str(GUNICORN_CONF))["workers"]

    def test_workers_need_redis(self):
        self.assertEqual(self.workers(ZONA_WEB_WORKERS="3"), 1)
        self.assertEqual(self.workers(ZONA_WEB_WORKERS="3", ZONA_REDIS_URL="unix:///run/x.sock"), 3)
        self.assertEqual(self.workers(ZONA_WEB_WORKERS="x", ZONA_REDIS_URL="unix:///run/x.sock"), 1)
        self.assertEqual(self.workers(ZONA_REDIS_URL="unix:///run/x.sock"), 1)
