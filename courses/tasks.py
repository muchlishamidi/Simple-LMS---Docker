import csv
import os
from datetime import datetime

from celery import shared_task
from django.conf import settings

from .mongo_service import (
    log_activity,
    record_learning_progress,
    get_course_completion_stats,
)


# ══════════════════════════════════════════════════════════════
# TASK 1 — send_enrollment_email (async, dipanggil saat enroll)
# ══════════════════════════════════════════════════════════════

@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def send_enrollment_email(self, user_id: int, course_id: int):
    """
    Kirim email konfirmasi enrollment.
    Parameter berupa ID (bukan object) karena harus JSON-serializable.
    """
    from .models import User, Course

    try:
        user = User.objects.get(pk=user_id)
        course = Course.objects.get(pk=course_id)
    except (User.DoesNotExist, Course.DoesNotExist) as exc:
        # Tidak perlu retry kalau datanya memang tidak ada
        return f"Gagal: user_id={user_id} atau course_id={course_id} tidak ditemukan"

    # Simulasi pengiriman email (ganti dengan django.core.mail.send_mail di production)
    print(f"[{datetime.now()}] Mengirim email ke {user.email}")
    print(f"Subject: Konfirmasi Enrollment - {course.name}")
    print(f"Body: Halo {user.first_name}, Anda berhasil mendaftar di course '{course.name}'.")

    log_activity(
        user_id=user_id,
        action="enrollment_email_sent",
        target_type="course",
        target_id=course_id,
    )

    return f"Email terkirim ke {user.email} untuk course '{course.name}'"


# ══════════════════════════════════════════════════════════════
# TASK 2 — generate_certificate (dipanggil saat course 100% selesai)
# ══════════════════════════════════════════════════════════════

@shared_task(bind=True, max_retries=2)
def generate_certificate(self, user_id: int, course_id: int):
    """
    Generate sertifikat sederhana (format .txt) saat student menyelesaikan
    100% konten sebuah course. Disimpan di media/certificates/.
    """
    from .models import User, Course

    user = User.objects.get(pk=user_id)
    course = Course.objects.get(pk=course_id)

    certs_dir = os.path.join(settings.BASE_DIR, "media", "certificates")
    os.makedirs(certs_dir, exist_ok=True)

    filename = f"certificate_user{user_id}_course{course_id}.txt"
    filepath = os.path.join(certs_dir, filename)

    content = (
        "=" * 50 + "\n"
        "          SERTIFIKAT PENYELESAIAN\n"
        + "=" * 50 + "\n\n"
        f"Diberikan kepada : {user.first_name} {user.last_name} ({user.username})\n"
        f"Atas penyelesaian : {course.name}\n"
        f"Pengajar          : {course.teacher.first_name} {course.teacher.last_name}\n"
        f"Tanggal           : {datetime.now().strftime('%d %B %Y')}\n\n"
        "Simple LMS - Generated automatically by Celery\n"
    )

    with open(filepath, "w") as f:
        f.write(content)

    log_activity(
        user_id=user_id,
        action="certificate_generated",
        target_type="course",
        target_id=course_id,
        metadata={"file": filename},
    )

    return {"status": "completed", "file": filename, "path": filepath}


# ══════════════════════════════════════════════════════════════
# TASK 3 — update_course_statistics (periodic, via Celery Beat)
# ══════════════════════════════════════════════════════════════

@shared_task
def update_course_statistics():
    """
    Periodic task — dijadwalkan lewat CELERY_BEAT_SCHEDULE di settings.py.
    Menghitung ulang jumlah enrollment per course dan menyimpan statistik
    global ke MongoDB (collection `daily_stats`) untuk histori.
    """
    from .models import Course, CourseMember, User
    from .mongo_service import get_mongo_db

    db = get_mongo_db()

    course_stats = []
    for course in Course.objects.all():
        member_count = CourseMember.objects.filter(course_id=course).count()
        course_stats.append({"course_id": course.id, "name": course.name, "members": member_count})

    snapshot = {
        "date": str(datetime.now().date()),
        "timestamp": datetime.now(),
        "total_courses": Course.objects.count(),
        "total_users": User.objects.count(),
        "total_enrollments": CourseMember.objects.count(),
        "courses": course_stats,
    }

    db.daily_stats.insert_one(snapshot)
    print(f"[update_course_statistics] {snapshot['date']}: "
          f"{snapshot['total_courses']} courses, {snapshot['total_enrollments']} enrollments")

    return {
        "total_courses": snapshot["total_courses"],
        "total_enrollments": snapshot["total_enrollments"],
    }


# ══════════════════════════════════════════════════════════════
# TASK 4 — export_course_report (async, trigger manual via endpoint)
# ══════════════════════════════════════════════════════════════

@shared_task(bind=True)
def export_course_report(self, course_id: int):
    """
    Generate laporan CSV untuk satu course: daftar member, role, dan progress.
    File disimpan di media/reports/.
    """
    from .models import Course, CourseMember, Progress

    course = Course.objects.get(pk=course_id)
    members = CourseMember.objects.filter(course_id=course).select_related("user_id")

    reports_dir = os.path.join(settings.BASE_DIR, "media", "reports")
    os.makedirs(reports_dir, exist_ok=True)

    filename = f"report_course{course_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    filepath = os.path.join(reports_dir, filename)

    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["username", "first_name", "last_name", "role", "contents_completed"])

        for member in members:
            completed = Progress.objects.filter(member=member, is_completed=True).count()
            writer.writerow([
                member.user_id.username,
                member.user_id.first_name,
                member.user_id.last_name,
                member.roles,
                completed,
            ])

    completion_stats = get_course_completion_stats(course_id)

    return {
        "status": "completed",
        "course": course.name,
        "file": filename,
        "path": filepath,
        "total_members": members.count(),
        "completion_stats": completion_stats,
    }
