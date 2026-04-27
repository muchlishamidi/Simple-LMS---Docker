from ninja import NinjaAPI
from ninja.errors import HttpError
from django.contrib.auth.hashers import make_password, check_password
from django.db import IntegrityError
from typing import List, Optional

from .models import User, Course, CourseMember, CourseContent, Progress
from .schemas import (
    RegisterIn, LoginIn, LoginOut, UpdateProfileIn, UserOut,
    CourseIn, CoursePatchIn, CourseOut, DetailCourseOut, PaginatedCourseOut,
    EnrollmentIn, EnrollmentOut, MyCourseOut,
    ProgressIn, ProgressOut,
)

api = NinjaAPI(
    title="Simple LMS API",
    version="1.0.0",
    description="REST API untuk Simple Learning Management System",
    urls_namespace="api",
)


def get_object_or_404(model, **kwargs):
    try:
        return model.objects.get(**kwargs)
    except model.DoesNotExist:
        raise HttpError(404, f"{model.__name__} tidak ditemukan")


# ══════════════════════════════════════════════════════════════
# AUTH ENDPOINTS
# ══════════════════════════════════════════════════════════════

@api.post("auth/register", response={201: UserOut}, tags=["Auth"])
def register(request, data: RegisterIn):
    """Register pengguna baru."""
    if User.objects.filter(username=data.username).exists():
        raise HttpError(400, "Username sudah digunakan")
    if data.role not in ['admin', 'instructor', 'student']:
        raise HttpError(400, "Role tidak valid. Pilih: admin, instructor, student")

    user = User.objects.create(
        username=data.username,
        email=data.email,
        first_name=data.first_name,
        last_name=data.last_name,
        role=data.role,
        password=make_password(data.password),
    )
    return 201, user


@api.post("auth/login", response=LoginOut, tags=["Auth"])
def login(request, data: LoginIn):
    """Login dengan username dan password."""
    try:
        user = User.objects.get(username=data.username)
    except User.DoesNotExist:
        raise HttpError(401, "Username atau password salah")

    if not check_password(data.password, user.password):
        raise HttpError(401, "Username atau password salah")

    return {"message": "Login berhasil", "user": user}


@api.get("auth/me", response=UserOut, tags=["Auth"])
def get_me(request, user_id: int):
    """Ambil data user yang sedang login (gunakan user_id sebagai parameter)."""
    return get_object_or_404(User, pk=user_id)


@api.put("auth/me", response=UserOut, tags=["Auth"])
def update_profile(request, user_id: int, data: UpdateProfileIn):
    """Update profil user."""
    user = get_object_or_404(User, pk=user_id)
    if data.first_name:
        user.first_name = data.first_name
    if data.last_name:
        user.last_name = data.last_name
    if data.email:
        user.email = data.email
    user.save()
    return user


# ══════════════════════════════════════════════════════════════
# COURSE ENDPOINTS — PUBLIC
# ══════════════════════════════════════════════════════════════

@api.get("courses", response=PaginatedCourseOut, tags=["Courses"])
def list_courses(
    request,
    search: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    category_id: Optional[int] = None,
    page: int = 1,
    page_size: int = 10,
):
    """List semua course dengan pagination dan filter opsional."""
    qs = Course.objects.select_related('teacher', 'category').all()

    if search:
        qs = qs.filter(name__icontains=search)
    if min_price is not None:
        qs = qs.filter(price__gte=min_price)
    if max_price is not None:
        qs = qs.filter(price__lte=max_price)
    if category_id is not None:
        qs = qs.filter(category_id=category_id)

    total = qs.count()
    offset = (page - 1) * page_size
    results = list(qs[offset:offset + page_size])

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "results": results,
    }


@api.get("courses/{id}", response=DetailCourseOut, tags=["Courses"])
def detail_course(request, id: int):
    """Detail course beserta daftar kontennya."""
    try:
        return Course.objects.select_related(
            'teacher', 'category'
        ).prefetch_related('coursecontent_set').get(pk=id)
    except Course.DoesNotExist:
        raise HttpError(404, "Course tidak ditemukan")


# ══════════════════════════════════════════════════════════════
# COURSE ENDPOINTS — PROTECTED (Instructor/Admin)
# ══════════════════════════════════════════════════════════════

@api.post("courses", response={201: CourseOut}, tags=["Courses"])
def create_course(request, data: CourseIn, teacher_id: int):
    """
    Buat course baru. Hanya untuk Instructor.
    Gunakan teacher_id dari user yang login dengan role instructor.
    """
    teacher = get_object_or_404(User, pk=teacher_id)
    if teacher.role != User.Role.INSTRUCTOR:
        raise HttpError(403, "Hanya instructor yang bisa membuat course")

    course = Course.objects.create(
        name=data.name,
        description=data.description,
        price=data.price,
        teacher=teacher,
    )
    course.refresh_from_db()
    return 201, Course.objects.select_related('teacher', 'category').get(pk=course.pk)


@api.patch("courses/{id}", response=CourseOut, tags=["Courses"])
def update_course(request, id: int, data: CoursePatchIn, user_id: int):
    """
    Update sebagian data course. Hanya owner (teacher) yang bisa mengubah.
    """
    course = get_object_or_404(Course, pk=id)
    user = get_object_or_404(User, pk=user_id)

    if course.teacher_id != user.id:
        raise HttpError(403, "Hanya owner course yang bisa mengubah data ini")

    if data.name is not None:
        course.name = data.name
    if data.description is not None:
        course.description = data.description
    if data.price is not None:
        if data.price < 0:
            raise HttpError(400, "Harga tidak boleh negatif")
        course.price = data.price

    course.save()
    return Course.objects.select_related('teacher', 'category').get(pk=course.pk)


@api.delete("courses/{id}", response={204: None}, tags=["Courses"])
def delete_course(request, id: int, user_id: int):
    """
    Hapus course. Hanya Admin yang bisa menghapus.
    """
    course = get_object_or_404(Course, pk=id)
    user = get_object_or_404(User, pk=user_id)

    if user.role != User.Role.ADMIN:
        raise HttpError(403, "Hanya admin yang bisa menghapus course")

    try:
        course.delete()
        return 204, None
    except Exception:
        raise HttpError(400, "Course tidak bisa dihapus karena masih memiliki relasi")


# ══════════════════════════════════════════════════════════════
# ENROLLMENT ENDPOINTS
# ══════════════════════════════════════════════════════════════

@api.post("enrollments", response={201: EnrollmentOut}, tags=["Enrollments"])
def enroll_course(request, data: EnrollmentIn, user_id: int):
    """
    Daftar ke course. Hanya untuk Student.
    """
    student = get_object_or_404(User, pk=user_id)
    if student.role != User.Role.STUDENT:
        raise HttpError(403, "Hanya student yang bisa mendaftar ke course")

    course = get_object_or_404(Course, pk=data.course_id)

    try:
        member = CourseMember.objects.create(
            course_id=course,
            user_id=student,
            roles='std',
        )
        return 201, {
            "id": member.id,
            "course_id": member.course_id_id,
            "roles": member.roles,
        }
    except IntegrityError:
        raise HttpError(409, "Anda sudah terdaftar di course ini")


@api.get("enrollments/my-courses", response=List[MyCourseOut], tags=["Enrollments"])
def my_courses(request, user_id: int):
    """
    Ambil semua course yang diikuti oleh student.
    """
    student = get_object_or_404(User, pk=user_id)
    enrollments = CourseMember.objects.filter(
        user_id=student
    ).select_related('course_id', 'course_id__teacher', 'course_id__category')
    return list(enrollments)


@api.post("enrollments/{id}/progress", response={201: ProgressOut}, tags=["Enrollments"])
def mark_progress(request, id: int, data: ProgressIn, user_id: int):
    """
    Tandai konten sebagai selesai. id adalah enrollment (CourseMember) id.
    """
    member = get_object_or_404(CourseMember, pk=id)
    student = get_object_or_404(User, pk=user_id)

    if member.user_id_id != student.id:
        raise HttpError(403, "Anda tidak memiliki akses ke enrollment ini")

    content = get_object_or_404(CourseContent, pk=data.content_id)

    from django.utils import timezone
    progress, created = Progress.objects.get_or_create(
        member=member,
        content=content,
        defaults={
            'is_completed': data.is_completed,
            'completed_at': timezone.now() if data.is_completed else None,
        }
    )

    if not created:
        progress.is_completed = data.is_completed
        progress.completed_at = timezone.now() if data.is_completed else None
        progress.save()

    return 201, progress