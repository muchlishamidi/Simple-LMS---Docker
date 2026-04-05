import csv
import django
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from courses.models import User, Category, Course, CourseMember, CourseContent, Comment


def create_initial_users():
    users = [
        {'username': 'dosen01', 'first_name': 'Budi',   'last_name': 'Santoso', 'role': 'instructor'},
        {'username': 'dosen02', 'first_name': 'Siti',   'last_name': 'Rahayu',  'role': 'instructor'},
        {'username': 'siswa01', 'first_name': 'Andi',   'last_name': 'Pratama', 'role': 'student'},
        {'username': 'siswa02', 'first_name': 'Bela',   'last_name': 'Safitri', 'role': 'student'},
        {'username': 'siswa03', 'first_name': 'Candra', 'last_name': 'Wijaya',  'role': 'student'},
        {'username': 'siswa04', 'first_name': 'Dina',   'last_name': 'Permata', 'role': 'student'},
        {'username': 'siswa05', 'first_name': 'Eko',    'last_name': 'Nugroho', 'role': 'student'},
    ]
    for data in users:
        user, created = User.objects.get_or_create(
            username=data['username'],
            defaults={
                'first_name': data['first_name'],
                'last_name': data['last_name'],
                'role': data['role'],
            }
        )
        if created:
            user.set_password('password123')
            user.save()
            print(f"[CREATED] User: {user.username} ({user.role})")
        else:
            print(f"[EXISTS]  User: {user.username}")


def create_initial_categories():
    data = [
        {'name': 'Pemrograman',       'parent': None},
        {'name': 'Jaringan',          'parent': None},
        {'name': 'Web Development',   'parent': 'Pemrograman'},
        {'name': 'Mobile Development','parent': 'Pemrograman'},
        {'name': 'Database',          'parent': 'Pemrograman'},
    ]
    for item in data:
        parent = Category.objects.get(name=item['parent']) if item['parent'] else None
        cat, created = Category.objects.get_or_create(name=item['name'], defaults={'parent': parent})
        status = "CREATED" if created else "EXISTS "
        print(f"[{status}] Category: {cat}")


def import_courses(csv_file):
    with open(csv_file, 'r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            teacher = User.objects.get(username=row['teacher_username'])
            course, created = Course.objects.get_or_create(
                name=row['name'],
                defaults={
                    'description': row['description'],
                    'price': int(row['price']),
                    'teacher': teacher,
                }
            )
            status = "CREATED" if created else "EXISTS "
            print(f"[{status}] Course: {course.name}")


def import_members(csv_file):
    with open(csv_file, 'r') as file:
        reader = csv.DictReader(file)
        for row in reader:
            course = Course.objects.get(name=row['course_name'])
            user = User.objects.get(username=row['username'])
            member, created = CourseMember.objects.get_or_create(
                course_id=course,
                user_id=user,
                defaults={'roles': row['roles']}
            )
            status = "CREATED" if created else "EXISTS "
            print(f"[{status}] Member: {user.username} -> {course.name}")


def seed_course_contents():
    """Bulk create konten untuk setiap course (dari referensi Chapter 5)."""
    courses = Course.objects.all()
    obj_create = []
    for course in courses:
        if not CourseContent.objects.filter(course_id=course).exists():
            for i in range(1, 4):
                obj_create.append(
                    CourseContent(
                        name=f'Materi {i} - {course.name}',
                        description=f'Deskripsi materi {i} untuk {course.name}',
                        order=i,
                        course_id=course,
                    )
                )
    if obj_create:
        CourseContent.objects.bulk_create(obj_create)
        print(f"[CREATED] {len(obj_create)} course contents (bulk_create)")
    else:
        print("[EXISTS]  Course contents sudah ada")


if __name__ == '__main__':
    print("=== Creating Users ===")
    create_initial_users()

    print("\n=== Creating Categories ===")
    create_initial_categories()

    print("\n=== Importing Courses ===")
    import_courses('courses/fixtures/courses.csv')

    print("\n=== Importing Members ===")
    import_members('courses/fixtures/members.csv')

    print("\n=== Seeding Course Contents (bulk_create) ===")
    seed_course_contents()

    print("\nImport selesai!")