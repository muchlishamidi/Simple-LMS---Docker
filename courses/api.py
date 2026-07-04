from ninja import NinjaAPI
from ninja.errors import HttpError
from ninja_simple_jwt.auth.views.api import mobile_auth_router
from ninja_simple_jwt.auth.ninja_auth import HttpJwtAuth
from celery.result import AsyncResult
from django.db import IntegrityError
from django.utils import timezone
from typing import List, Optional

from .models import User, Course, CourseMember, CourseContent, Comment, Progress
from .schemas import (
    RegisterIn, UpdateProfileIn, UserOut,
    CourseIn, CoursePatchIn, CourseOut, DetailCourseOut, PaginatedCourseOut,
    CourseOrdering,
    EnrollmentIn, EnrollmentOut, MyCourseOut,
    ProgressIn, ProgressOut,
    CommentIn, CommentUpdateIn, CommentOut,
    PopularCourseOut, DailySummaryOut, UserActivityOut,
    TaskTriggeredOut, TaskStatusOut,
)
from .helpers import (
    get_authenticated_user, check_course_owner,
    check_owner_or_superadmin, check_enrollment,
    calculate_course_progress,
)
from .cache import (
    get_cached_course_list, set_cached_course_list,
    get_cached_course_detail, set_cached_course_detail,
    invalidate_course_cache, rate_limited, get_client_ip,
)
from .mongo_service import (
    log_activity, record_learning_progress,
    get_popular_courses, get_user_activity_summary, get_daily_activity_summary,
)
from .serializers import serialize_course, serialize_course_detail
from .tasks import send_enrollment_email, generate_certificate, export_course_report
from .response import success, created, no_content, paginated, register_error_handlers

api = NinjaAPI(
    title="Simple LMS API",
    version="1.0.0",
    description="REST API Simple LMS — JWT Auth, Redis Cache, MongoDB Analytics, Celery Async Tasks",
)

# Endpoint /auth/sign-in dan /auth/token-refresh disediakan otomatis oleh library.
api.add_router("/auth/", mobile_auth_router)

# Dipakai sebagai parameter auth= pada endpoint yang butuh login.
apiAuth = HttpJwtAuth()

# Daftarkan global error handler supaya error response konsisten
register_error_handlers(api)


def get_object_or_404(model, **kwargs):
    try:
        return model.objects.get(**kwargs)
    except model.DoesNotExist:
        raise HttpError(404, f"{model.__name__} tidak ditemukan")


# ══════════════════════════════════════════════════════════════
# AUTH ENDPOINTS — TAMBAHAN (di luar yang disediakan library)
# ══════════════════════════════════════════════════════════════

@api.post("auth/register", tags=["Auth"])
def register(request, data: RegisterIn):
    """Register pengguna baru, dengan field `role` (admin/instructor/student)."""
    if User.objects.filter(username=data.username).exists():
        raise HttpError(400, "Username sudah digunakan")
    if User.objects.filter(email=data.email).exists():
        raise HttpError(400, "Email sudah digunakan")
    if data.role not in ['admin', 'instructor', 'student']:
        raise HttpError(400, "Role tidak valid. Pilih: admin, instructor, student")

    new_user = User.objects.create_user(
        username=data.username,
        password=data.password,
        email=data.email,
        first_name=data.first_name,
        last_name=data.last_name,
        role=data.role,
    )
    from django.http import JsonResponse
    user_data = {
        "id": new_user.id,
        "username": new_user.username,
        "email": new_user.email,
        "first_name": new_user.first_name,
        "last_name": new_user.last_name,
        "role": new_user.role,
    }
    return JsonResponse(created(user_data, "Registrasi berhasil"), status=201)


@api.get("auth/me", auth=apiAuth, tags=["Auth"])
def get_me(request):
    """Mengambil data user yang sedang login."""
    user = get_authenticated_user(request)
    from django.http import JsonResponse
    return JsonResponse(success({
        "id": user.id, "username": user.username, "email": user.email,
        "first_name": user.first_name, "last_name": user.last_name, "role": user.role,
    }))


@api.put("auth/me", auth=apiAuth, tags=["Auth"])
def update_profile(request, data: UpdateProfileIn):
    """Mengubah profil user yang sedang login."""
    user = get_authenticated_user(request)
    if data.first_name:
        user.first_name = data.first_name
    if data.last_name:
        user.last_name = data.last_name
    if data.email:
        user.email = data.email
    user.save()
    from django.http import JsonResponse
    return JsonResponse(success({
        "id": user.id, "username": user.username, "email": user.email,
        "first_name": user.first_name, "last_name": user.last_name, "role": user.role,
    }, "Profil berhasil diperbarui"))


# ══════════════════════════════════════════════════════════════
# COURSE ENDPOINTS — PUBLIC
# Redis caching + rate limiting (60 request/menit per IP) diterapkan
# di sini karena endpoint ini publik dan paling rawan diakses berlebihan.
# ══════════════════════════════════════════════════════════════

@api.get("courses", tags=["Courses"])
@rate_limited(lambda request: get_client_ip(request))
def list_courses(
    request,
    search: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    category_id: Optional[int] = None,
    ordering: CourseOrdering = CourseOrdering.created_desc,
    page: int = 1,
    page_size: int = 10,
):
    """
    List semua course dengan pagination, filter, dan sorting.
    Endpoint publik, response di-cache 5 menit di Redis.

    Sorting options (ordering):
    - name / -name
    - price / -price
    - created_at / -created_at (default)
    """
    if page_size > 50:
        page_size = 50  # batasi maksimal 50 item per halaman

    query_params = {
        "search": search, "min_price": min_price, "max_price": max_price,
        "category_id": category_id, "ordering": ordering.value,
        "page": page, "page_size": page_size,
    }

    cached = get_cached_course_list(query_params)
    if cached is not None:
        return cached

    qs = Course.objects.select_related('teacher', 'category').all()

    if search:
        qs = qs.filter(name__icontains=search)
    if min_price is not None:
        qs = qs.filter(price__gte=min_price)
    if max_price is not None:
        qs = qs.filter(price__lte=max_price)
    if category_id is not None:
        qs = qs.filter(category_id=category_id)

    # Sorting — nilai ordering dari enum sudah berformat Django ORM
    # (prefix "-" untuk descending, tanpa prefix untuk ascending)
    qs = qs.order_by(ordering.value)

    total = qs.count()
    total_pages = -(-total // page_size)  # ceiling division
    offset = (page - 1) * page_size
    results = list(qs[offset:offset + page_size])

    data = paginated(
        results=[serialize_course(c) for c in results],
        total=total,
        page=page,
        page_size=page_size,
    )
    # Tambah total_pages ke dalam data["data"] karena paginated() sudah hitung
    data["data"]["ordering"] = ordering.value

    set_cached_course_list(query_params, data)
    return data


@api.get("courses/{id}", tags=["Courses"])
@rate_limited(lambda request: get_client_ip(request))
def detail_course(request, id: int):
    """Detail course beserta daftar kontennya. Endpoint publik, di-cache 10 menit."""
    cached = get_cached_course_detail(id)
    if cached is not None:
        return cached

    try:
        course = Course.objects.select_related(
            'teacher', 'category'
        ).prefetch_related('coursecontent_set').get(pk=id)
    except Course.DoesNotExist:
        raise HttpError(404, "Course tidak ditemukan")

    data = success(serialize_course_detail(course))
    set_cached_course_detail(id, data)

    user_id = getattr(getattr(request, 'user', None), 'id', None)
    log_activity(
        user_id=user_id,
        action="view_course",
        target_type="course",
        target_id=id,
        metadata={"course_name": course.name},
    )

    return data


# ══════════════════════════════════════════════════════════════
# COURSE ENDPOINTS — PROTECTED
# Create: semua authenticated user, otomatis jadi teacher
# Update: hanya course owner
# Delete: course owner ATAU superadmin
# Setiap perubahan data course memicu cache invalidation.
# ══════════════════════════════════════════════════════════════

@api.post("courses", auth=apiAuth, tags=["Courses"])
def create_course(request, data: CourseIn):
    """Buat course baru. Semua user yang login bisa membuat dan otomatis jadi teacher."""
    user = get_authenticated_user(request)

    course = Course.objects.create(
        name=data.name,
        description=data.description,
        price=data.price,
        teacher=user,
    )
    invalidate_course_cache()
    course_data = serialize_course(
        Course.objects.select_related('teacher', 'category').get(pk=course.pk)
    )
    from django.http import JsonResponse
    import json
    return JsonResponse(created(course_data, "Course berhasil dibuat"), status=201)


@api.patch("courses/{id}", auth=apiAuth, tags=["Courses"])
def update_course(request, id: int, data: CoursePatchIn):
    """Update sebagian data course. Hanya owner (teacher) yang boleh mengedit."""
    user = get_authenticated_user(request)
    course = get_object_or_404(Course, pk=id)

    check_course_owner(course, user)

    if data.name is not None:
        course.name = data.name
    if data.description is not None:
        course.description = data.description
    if data.price is not None:
        if data.price < 0:
            raise HttpError(400, "Harga tidak boleh negatif")
        course.price = data.price

    course.save()
    invalidate_course_cache(course_id=id)
    course_data = serialize_course(
        Course.objects.select_related('teacher', 'category').get(pk=course.pk)
    )
    from django.http import JsonResponse
    return JsonResponse(success(course_data, "Course berhasil diperbarui"))


@api.delete("courses/{id}", auth=apiAuth, tags=["Courses"])
def delete_course(request, id: int):
    """Hapus course. Hanya course owner atau superadmin."""
    user = get_authenticated_user(request)
    course = get_object_or_404(Course, pk=id)

    check_owner_or_superadmin(course.teacher, user)

    try:
        course.delete()
        invalidate_course_cache(course_id=id)
        from django.http import JsonResponse
        return JsonResponse(no_content("Course berhasil dihapus"))
    except Exception:
        raise HttpError(400, "Course tidak bisa dihapus karena masih memiliki relasi")


# ══════════════════════════════════════════════════════════════
# ENROLLMENT ENDPOINTS
# enroll_course memicu: activity log (Mongo) + send_enrollment_email (Celery)
# mark_progress memicu: learning analytics (Mongo) + generate_certificate
#                        (Celery) otomatis saat progress mencapai 100%
# ══════════════════════════════════════════════════════════════

@api.post("enrollments", auth=apiAuth, tags=["Enrollments"])
def enroll_course(request, data: EnrollmentIn):
    """Daftar ke course. Semua user yang login boleh enroll."""
    user = get_authenticated_user(request)
    course = get_object_or_404(Course, pk=data.course_id)

    if CourseMember.objects.filter(user_id=user, course_id=course).exists():
        raise HttpError(400, "Anda sudah terdaftar di course ini")

    try:
        member = CourseMember.objects.create(
            course_id=course,
            user_id=user,
            roles='std',
        )
    except IntegrityError:
        raise HttpError(409, "Anda sudah terdaftar di course ini")

    log_activity(
        user_id=user.id,
        action="enroll",
        target_type="course",
        target_id=course.id,
        metadata={"course_name": course.name},
    )

    send_enrollment_email.delay(user.id, course.id)

    from django.http import JsonResponse
    return JsonResponse(created({
        "id": member.id,
        "course_id": member.course_id_id,
        "roles": member.roles,
    }, "Berhasil mendaftar ke course"), status=201)


@api.get("enrollments/my-courses", auth=apiAuth, tags=["Enrollments"])
def my_courses(request):
    """Mengambil semua course yang diikuti oleh user yang sedang login."""
    user = get_authenticated_user(request)
    enrollments = CourseMember.objects.filter(
        user_id=user
    ).select_related('course_id', 'course_id__teacher', 'course_id__category')

    from django.http import JsonResponse
    from .serializers import serialize_course
    data = [
        {
            "id": e.id,
            "roles": e.roles,
            "course": serialize_course(e.course_id),
        }
        for e in enrollments
    ]
    return JsonResponse(success(data))


@api.post("enrollments/{id}/progress", auth=apiAuth, tags=["Enrollments"])
def mark_progress(request, id: int, data: ProgressIn):
    """Menandai konten sebagai selesai. id adalah id Enrollment (CourseMember)."""
    user = get_authenticated_user(request)
    member = get_object_or_404(CourseMember, pk=id)

    check_owner_or_superadmin(member.user_id, user)

    content = get_object_or_404(CourseContent, pk=data.content_id)

    progress, prog_created = Progress.objects.get_or_create(
        member=member,
        content=content,
        defaults={
            'is_completed': data.is_completed,
            'completed_at': timezone.now() if data.is_completed else None,
        }
    )

    if not prog_created:
        progress.is_completed = data.is_completed
        progress.completed_at = timezone.now() if data.is_completed else None
        progress.save()

    percentage, completed_ids = calculate_course_progress(member)
    record_learning_progress(
        user_id=member.user_id_id,
        course_id=member.course_id_id,
        enrollment_id=member.id,
        progress_percentage=percentage,
        completed_content_ids=completed_ids,
    )

    if percentage >= 100:
        generate_certificate.delay(member.user_id_id, member.course_id_id)

    from django.http import JsonResponse
    return JsonResponse(created({
        "id": progress.id,
        "is_completed": progress.is_completed,
        "completed_at": progress.completed_at.isoformat() if progress.completed_at else None,
        "progress_percentage": percentage,
        "certificate_triggered": percentage >= 100,
    }, "Progress berhasil disimpan"), status=201)


# ══════════════════════════════════════════════════════════════
# COMMENT ENDPOINTS
# post_comment memicu activity log ke MongoDB.
# ══════════════════════════════════════════════════════════════

@api.post("comments", auth=apiAuth, tags=["Comments"])
def post_comment(request, data: CommentIn):
    """Tambah komentar. Hanya user yang terdaftar (enrolled) di course terkait."""
    user = get_authenticated_user(request)
    content = get_object_or_404(CourseContent, pk=data.content_id)

    check_enrollment(user, content.course_id)

    member = CourseMember.objects.get(user_id=user, course_id=content.course_id)
    comment = Comment.objects.create(
        comment=data.comment,
        content_id=content,
        member_id=member,
    )

    log_activity(
        user_id=user.id,
        action="post_comment",
        target_type="content",
        target_id=content.id,
        metadata={"course_id": content.course_id_id},
    )

    from django.http import JsonResponse
    return JsonResponse(created({
        "id": comment.id,
        "comment": comment.comment,
        "content_id": comment.content_id_id,
        "member_id": comment.member_id_id,
    }, "Komentar berhasil ditambahkan"), status=201)


@api.put("comments/{id}", auth=apiAuth, tags=["Comments"])
def update_comment(request, id: int, data: CommentUpdateIn):
    """Update komentar. Hanya pemilik komentar yang boleh mengedit."""
    user = get_authenticated_user(request)
    comment = get_object_or_404(Comment, pk=id)

    check_owner_or_superadmin(comment.member_id.user_id, user)

    comment.comment = data.comment
    comment.save()

    from django.http import JsonResponse
    return JsonResponse(success({
        "id": comment.id,
        "comment": comment.comment,
        "content_id": comment.content_id_id,
        "member_id": comment.member_id_id,
    }, "Komentar berhasil diperbarui"))


@api.delete("comments/{id}", auth=apiAuth, tags=["Comments"])
def delete_comment(request, id: int):
    """
    Hapus komentar. Bisa dilakukan oleh:
    - pemilik komentar
    - pemilik course (teacher dari course terkait)
    - superadmin
    """
    user = get_authenticated_user(request)
    comment = Comment.objects.select_related(
        'member_id__user_id', 'content_id__course_id__teacher'
    ).filter(pk=id).first()
    if comment is None:
        raise HttpError(404, "Comment tidak ditemukan")

    is_comment_owner = (comment.member_id.user_id == user)
    is_course_owner = (comment.content_id.course_id.teacher == user)
    is_superadmin = user.is_superuser

    if not (is_comment_owner or is_course_owner or is_superadmin):
        raise HttpError(403, "Anda tidak memiliki izin untuk menghapus komentar ini")

    comment.delete()
    from django.http import JsonResponse
    return JsonResponse(no_content("Komentar berhasil dihapus"))


# ══════════════════════════════════════════════════════════════
# ANALYTICS ENDPOINTS (MongoDB aggregation) — Admin only
# ══════════════════════════════════════════════════════════════

@api.get("analytics/popular-courses", auth=apiAuth, tags=["Analytics"])
def popular_courses(request, limit: int = 5):
    """Top course berdasarkan jumlah view_course (aggregation MongoDB). Admin only."""
    user = get_authenticated_user(request)
    if not user.is_superuser and user.role != User.Role.ADMIN:
        raise HttpError(403, "Hanya admin yang bisa mengakses analytics")
    from django.http import JsonResponse
    return JsonResponse(success(get_popular_courses(limit=limit)))


@api.get("analytics/user-activity/{user_id}", auth=apiAuth, tags=["Analytics"])
def user_activity(request, user_id: int):
    """Ringkasan aktivitas seorang user (aggregation MongoDB). Admin only."""
    requester = get_authenticated_user(request)
    if not requester.is_superuser and requester.role != User.Role.ADMIN:
        raise HttpError(403, "Hanya admin yang bisa mengakses analytics")
    from django.http import JsonResponse
    return JsonResponse(success(get_user_activity_summary(user_id)))


@api.get("analytics/daily-summary", auth=apiAuth, tags=["Analytics"])
def daily_summary(request, days: int = 7):
    """Ringkasan aktivitas harian, N hari terakhir (aggregation MongoDB). Admin only."""
    user = get_authenticated_user(request)
    if not user.is_superuser and user.role != User.Role.ADMIN:
        raise HttpError(403, "Hanya admin yang bisa mengakses analytics")
    from django.http import JsonResponse
    return JsonResponse(success(get_daily_activity_summary(days=days)))


# ══════════════════════════════════════════════════════════════
# REPORT ENDPOINTS (Celery async — export_course_report)
# ══════════════════════════════════════════════════════════════

@api.post("reports/generate/{course_id}", auth=apiAuth, tags=["Reports"])
def generate_report(request, course_id: int):
    """Trigger pembuatan laporan CSV course secara async. Hanya course owner/admin."""
    user = get_authenticated_user(request)
    course = get_object_or_404(Course, pk=course_id)
    check_owner_or_superadmin(course.teacher, user)

    task = export_course_report.delay(course_id)
    from django.http import JsonResponse
    return JsonResponse(created({
        "task_id": task.id,
        "status": "processing",
    }, f"Report untuk course '{course.name}' sedang dibuat"), status=201)


@api.get("reports/status/{task_id}", auth=apiAuth, tags=["Reports"])
def report_status(request, task_id: str):
    """Cek status & hasil task report generation."""
    result = AsyncResult(task_id)
    from django.http import JsonResponse

    if result.ready():
        return JsonResponse(success({
            "task_id": task_id,
            "status": result.status,
            "result": result.result,
        }))
    return JsonResponse(success({
        "task_id": task_id,
        "status": result.status,
        "result": None,
    }, "Task masih dalam proses"))