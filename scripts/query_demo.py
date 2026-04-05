import os
import sys
import django
import time

sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection, reset_queries
from django.conf import settings
from django.db.models import Count, Avg, Max, Min, Q

settings.DEBUG = True

from courses.models import Course, CourseMember, CourseContent, Comment, User


def benchmark(label, func):
    reset_queries()
    start = time.time()
    func()
    elapsed = (time.time() - start) * 1000
    query_count = len(connection.queries)
    print(f"\n{'='*55}")
    print(f"Benchmark: {label}")
    print(f"Queries   : {query_count}")
    print(f"Time      : {elapsed:.2f}ms")
    print(f"{'='*55}")
    return query_count


def n_plus_1_teacher():
    courses = Course.objects.all()
    for course in courses:
        _ = course.teacher.username


def optimized_teacher():
    courses = Course.objects.select_related('teacher').all()
    for course in courses:
        _ = course.teacher.username


def n_plus_1_members():
    courses = Course.objects.all()
    for course in courses:
        count = CourseMember.objects.filter(course_id=course).count()
        _ = count


def optimized_members():
    courses = Course.objects.annotate(member_count=Count('coursemember')).all()
    for course in courses:
        _ = course.member_count


def optimized_for_listing():
    courses = Course.objects.for_listing()
    for course in courses:
        _ = course.teacher.username
        _ = course.member_count
        _ = course.content_count


def optimized_dashboard():
    student = User.objects.filter(role=User.Role.STUDENT).first()
    if not student:
        return
    enrollments = CourseMember.objects.for_student_dashboard(student)
    for e in enrollments:
        _ = e.course_id.name
        _ = e.course_id.teacher.username


def demo_aggregate():
    stats = Course.objects.aggregate(
        total=Count('id'),
        avg_price=Avg('price'),
        max_price=Max('price'),
        min_price=Min('price'),
    )
    print(f"\n  Statistik Course:")
    print(f"  Total         : {stats['total']}")
    print(f"  Rata-rata     : Rp {stats['avg_price']:,.0f}" if stats['avg_price'] else "  Rata-rata     : -")
    print(f"  Tertinggi     : Rp {stats['max_price']:,}" if stats['max_price'] else "  Tertinggi     : -")
    print(f"  Terendah      : Rp {stats['min_price']:,}" if stats['min_price'] else "  Terendah      : -")


if __name__ == '__main__':
    print("\n" + "="*55)
    print("QUERY OPTIMIZATION DEMO — Simple LMS")
    print("="*55)

    print("\nList course + teacher")
    q1 = benchmark("N+1 Problem", n_plus_1_teacher)
    q2 = benchmark("select_related('teacher')", optimized_teacher)
    print(f"\n  Improvement: {q1} queries -> {q2} queries ({round((1 - q2/q1)*100) if q1 else 0}% lebih sedikit)")

    print("\nList course + jumlah member")
    q3 = benchmark("N+1 Problem (filter per course)", n_plus_1_members)
    q4 = benchmark("annotate(Count)", optimized_members)
    print(f"\n  Improvement: {q3} queries -> {q4} queries ({round((1 - q4/q3)*100) if q3 else 0}% lebih sedikit)")

    print("\nCourse.objects.for_listing()")
    benchmark("for_listing() — select_related + prefetch + annotate", optimized_for_listing)

    print("\nCourseMember.objects.for_student_dashboard()")
    benchmark("for_student_dashboard()", optimized_dashboard)

    print("\nAggregate statistik")
    benchmark("aggregate()", demo_aggregate)