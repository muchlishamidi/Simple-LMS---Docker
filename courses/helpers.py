from ninja.errors import HttpError

from .models import User, CourseMember


def get_authenticated_user(request):
    """
    Mendapatkan objek User lengkap dari request yang terautentikasi.

    HttpJwtAuth secara default memakai stateless auth (request.user hanya
    berisi klaim dari JWT, bukan objek User penuh dari database), jadi kita
    ambil ulang dari database agar field seperti `role` ikut tersedia.
    """
    return User.objects.get(pk=request.user.id)


def check_course_owner(course, user):
    """Memeriksa apakah user adalah pemilik (teacher) course."""
    if course.teacher != user:
        raise HttpError(403, "Hanya pemilik course yang dapat melakukan aksi ini")


def check_owner_or_superadmin(obj_owner, user):
    """Memeriksa apakah user adalah pemilik objek atau superadmin."""
    if obj_owner != user and not user.is_superuser:
        raise HttpError(403, "Anda tidak memiliki izin untuk melakukan aksi ini")


def check_enrollment(user, course):
    """Memeriksa apakah user terdaftar (enrolled) di course tertentu."""
    if not CourseMember.objects.filter(user_id=user, course_id=course).exists():
        raise HttpError(403, "Anda tidak terdaftar di course ini")


def calculate_course_progress(member):
    """
    Menghitung persentase progress belajar seorang member dalam course-nya.
    Return: (progress_percentage: float, completed_content_ids: list[int])
    """
    from .models import CourseContent, Progress

    total_contents = CourseContent.objects.filter(course_id=member.course_id).count()
    if total_contents == 0:
        return 0.0, []

    completed_ids = list(
        Progress.objects.filter(member=member, is_completed=True)
        .values_list('content_id', flat=True)
    )
    percentage = round((len(completed_ids) / total_contents) * 100, 2)
    return percentage, completed_ids