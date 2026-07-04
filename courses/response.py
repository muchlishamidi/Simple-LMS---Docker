"""
Consistent response format untuk semua endpoint API.

Semua response dibungkus format standar:
  Success: {"success": true, "data": {...}, "message": "OK"}
  Error:   {"success": false, "error": "...", "code": 404}

Ini membuat response mudah dikonsumsi client karena strukturnya
selalu konsisten, terlepas dari jenis data yang dikembalikan.
"""
from ninja import NinjaAPI
from ninja.errors import HttpError, ValidationError
from django.http import HttpRequest


def success(data, message: str = "OK") -> dict:
    return {
        "success": True,
        "message": message,
        "data": data,
    }


def created(data, message: str = "Berhasil dibuat") -> dict:
    return {
        "success": True,
        "message": message,
        "data": data,
    }


def no_content(message: str = "Berhasil dihapus") -> dict:
    return {
        "success": True,
        "message": message,
        "data": None,
    }


def paginated(results, total: int, page: int, page_size: int) -> dict:
    return {
        "success": True,
        "message": "OK",
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": -(-total // page_size),  # ceiling division
            "results": results,
        }
    }


def register_error_handlers(api: NinjaAPI):
    """
    Mendaftarkan global error handler supaya error response juga
    mengikuti format yang sama (bukan format default Django Ninja).
    """
    @api.exception_handler(HttpError)
    def http_error_handler(request: HttpRequest, exc: HttpError):
        from django.http import JsonResponse
        return JsonResponse(
            {
                "success": False,
                "message": str(exc.message),
                "data": None,
            },
            status=exc.status_code,
        )

    @api.exception_handler(ValidationError)
    def validation_error_handler(request: HttpRequest, exc: ValidationError):
        from django.http import JsonResponse
        return JsonResponse(
            {
                "success": False,
                "message": "Validasi input gagal",
                "data": exc.errors,
            },
            status=422,
        )