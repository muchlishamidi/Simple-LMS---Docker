"""
Redis caching utilities untuk Course list & detail, plus rate limiting.

Sengaja memakai raw redis-py client (bukan Django cache framework)
supaya:
1. Key di Redis terlihat persis (tanpa prefix/versioning tambahan dari
   Django), sehingga mudah dicek manual lewat redis-cli.
2. Cache invalidation dengan SCAN pattern matching bisa dilakukan secara
   eksplisit dan konsisten lintas versi Django/django-redis.

Key pattern:
    course:list:<md5_hash_of_query_params>   (TTL 5 menit)
    course:detail:<id>                       (TTL 10 menit)
    ratelimit:<identifier>                   (TTL 60 detik, fixed window)
"""
import hashlib
import json

import redis
from django.conf import settings
from ninja.errors import HttpError

_redis_cache = redis.Redis(
    host=settings.REDIS_HOST, port=settings.REDIS_PORT,
    db=settings.REDIS_CACHE_DB, decode_responses=True,
)

_redis_ratelimit = redis.Redis(
    host=settings.REDIS_HOST, port=settings.REDIS_PORT,
    db=settings.REDIS_RATELIMIT_DB, decode_responses=True,
)


# ── Course List & Detail Caching ─────────────────────────────

def _list_cache_key(query_params: dict) -> str:
    raw = json.dumps(query_params, sort_keys=True)
    digest = hashlib.md5(raw.encode()).hexdigest()
    return f"course:list:{digest}"


def _detail_cache_key(course_id: int) -> str:
    return f"course:detail:{course_id}"


def get_cached_course_list(query_params: dict):
    raw = _redis_cache.get(_list_cache_key(query_params))
    return json.loads(raw) if raw else None


def set_cached_course_list(query_params: dict, data: dict):
    _redis_cache.set(
        _list_cache_key(query_params),
        json.dumps(data),
        ex=settings.CACHE_TTL_COURSE_LIST,
    )


def get_cached_course_detail(course_id: int):
    raw = _redis_cache.get(_detail_cache_key(course_id))
    return json.loads(raw) if raw else None


def set_cached_course_detail(course_id: int, data: dict):
    _redis_cache.set(
        _detail_cache_key(course_id),
        json.dumps(data),
        ex=settings.CACHE_TTL_COURSE_DETAIL,
    )


def invalidate_course_cache(course_id: int = None):
    """
    Cache invalidation strategy:
    - Semua varian 'course:list:*' dihapus sekaligus (SCAN + DELETE),
      karena key list bergantung pada kombinasi filter/page yang
      jumlahnya tidak terbatas.
    - 'course:detail:<id>' dihapus spesifik jika course_id diberikan.

    Dipanggil setiap kali ada create/update/delete pada Course.
    """
    for key in _redis_cache.scan_iter("course:list:*"):
        _redis_cache.delete(key)

    if course_id is not None:
        _redis_cache.delete(_detail_cache_key(course_id))


# ── Rate Limiting (Fixed Window, default 60 request / 60 detik) ──

def check_rate_limit(identifier: str):
    """Fixed-window rate limiting menggunakan Redis INCR + EXPIRE (atomik)."""
    key = f"ratelimit:{identifier}"
    current = _redis_ratelimit.incr(key)

    if current == 1:
        _redis_ratelimit.expire(key, settings.RATE_LIMIT_WINDOW_SECONDS)

    if current > settings.RATE_LIMIT_MAX_REQUESTS:
        ttl = _redis_ratelimit.ttl(key)
        raise HttpError(
            429,
            f"Rate limit terlampaui ({settings.RATE_LIMIT_MAX_REQUESTS} request/menit). "
            f"Coba lagi dalam {ttl} detik."
        )


def rate_limited(identifier_func):
    """Decorator endpoint Django Ninja. identifier_func(request) -> str unik."""
    def decorator(func):
        def wrapper(request, *args, **kwargs):
            check_rate_limit(identifier_func(request))
            return func(request, *args, **kwargs)
        return wrapper
    return decorator


def get_client_ip(request) -> str:
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")
