"""Umumiy kesh (Redis) — bir nechta backend jarayoni (gunicorn worker'lar, bot, PRBC worker) uchun bitta.

Redis to'xtab qolsa sayt yiqilmasin: o'qish «yo'q» qaytaradi, yozish o'tkazib yuboriladi, `add` (qulf) — «olindi»
deb hisoblanadi (ish to'xtab qolgandan ko'ra takror bajarilgani yaxshi). Ogohlantirish logga daqiqada bir marta.
"""
import logging
import time

from django.core.cache.backends.base import DEFAULT_TIMEOUT
from django.core.cache.backends.redis import RedisCache
from redis.exceptions import RedisError

log = logging.getLogger(__name__)
_warned = [0.0]


def _warn(e):
    now = time.monotonic()
    if now - _warned[0] > 60:
        _warned[0] = now
        log.warning("Redis kesh ishlamayapti (%s) — keshsiz davom etiladi", e)


class SafeRedisCache(RedisCache):
    def _try(self, fn, fallback, *args):
        try:
            return fn(*args)
        except (RedisError, OSError) as e:
            _warn(e)
            return fallback

    def get(self, key, default=None, version=None):
        return self._try(super().get, default, key, default, version)

    def set(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        return self._try(super().set, None, key, value, timeout, version)

    def add(self, key, value, timeout=DEFAULT_TIMEOUT, version=None):
        return self._try(super().add, True, key, value, timeout, version)

    def touch(self, key, timeout=DEFAULT_TIMEOUT, version=None):
        return self._try(super().touch, False, key, timeout, version)

    def delete(self, key, version=None):
        return self._try(super().delete, False, key, version)

    def has_key(self, key, version=None):
        return self._try(super().has_key, False, key, version)

    def incr(self, key, delta=1, version=None):
        return self._try(super().incr, delta, key, delta, version)

    def get_many(self, keys, version=None):
        return self._try(super().get_many, {}, keys, version)

    def set_many(self, data, timeout=DEFAULT_TIMEOUT, version=None):
        return self._try(super().set_many, [], data, timeout, version)

    def delete_many(self, keys, version=None):
        return self._try(super().delete_many, None, keys, version)

    def clear(self):
        return self._try(super().clear, None)
