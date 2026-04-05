from django.db import models
from django.contrib.auth.models import AbstractUser

from .managers import CourseManager, CourseMemberManager


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        INSTRUCTOR = 'instructor', 'Instructor'
        STUDENT = 'student', 'Student'

    role = models.CharField(
        "peran",
        max_length=20,
        choices=Role.choices,
        default=Role.STUDENT
    )

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    class Meta:
        verbose_name = "Pengguna"
        verbose_name_plural = "Pengguna"


class Category(models.Model):
    name = models.CharField("nama kategori", max_length=100)
    parent = models.ForeignKey(
        "self",
        verbose_name="kategori induk",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children"
    )

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} > {self.name}"
        return self.name

    class Meta:
        verbose_name = "Kategori"
        verbose_name_plural = "Kategori"


class Course(models.Model):
    name = models.CharField("nama matkul", max_length=100)
    description = models.TextField("deskripsi", default='-')
    price = models.IntegerField("harga", default=10000)
    image = models.ImageField("gambar", null=True, blank=True)
    teacher = models.ForeignKey(
        User,
        verbose_name="pengajar",
        on_delete=models.RESTRICT,
        limit_choices_to={'role': User.Role.INSTRUCTOR}
    )
    category = models.ForeignKey(
        Category,
        verbose_name="kategori",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="courses"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CourseManager()

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Mata Kuliah"
        verbose_name_plural = "Mata Kuliah"
        indexes = [
            models.Index(fields=['name'], name='idx_course_name'),
            models.Index(fields=['price'], name='idx_course_price'),
        ]


ROLE_OPTIONS = [
    ('std', 'Siswa'),
    ('ast', 'Asisten'),
]


class CourseMember(models.Model):
    course_id = models.ForeignKey(
        Course,
        verbose_name="matkul",
        on_delete=models.RESTRICT
    )
    user_id = models.ForeignKey(
        User,
        verbose_name="siswa",
        on_delete=models.RESTRICT,
        limit_choices_to={'role': User.Role.STUDENT}
    )
    roles = models.CharField(
        "peran",
        max_length=3,
        choices=ROLE_OPTIONS,
        default='std'
    )

    objects = CourseMemberManager()

    def __str__(self):
        return f"{self.user_id} - {self.course_id} ({self.roles})"

    class Meta:
        verbose_name = "Anggota Kelas"
        verbose_name_plural = "Anggota Kelas"
        unique_together = ('course_id', 'user_id')


class CourseContent(models.Model):
    name = models.CharField("judul konten", max_length=200)
    description = models.TextField("deskripsi", default='-')
    video_url = models.CharField('URL Video', max_length=200, null=True, blank=True)
    file_attachment = models.FileField("File", null=True, blank=True)
    order = models.PositiveIntegerField("urutan", default=0)
    course_id = models.ForeignKey(
        Course,
        verbose_name="matkul",
        on_delete=models.RESTRICT
    )
    parent_id = models.ForeignKey(
        "self",
        verbose_name="induk",
        on_delete=models.RESTRICT,
        null=True,
        blank=True
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Konten Kelas"
        verbose_name_plural = "Konten Kelas"
        ordering = ['order']


class Comment(models.Model):
    content_id = models.ForeignKey(
        CourseContent,
        verbose_name="konten",
        on_delete=models.CASCADE
    )
    member_id = models.ForeignKey(
        CourseMember,
        verbose_name="pengguna",
        on_delete=models.CASCADE
    )
    comment = models.TextField('komentar')

    def __str__(self):
        return f"Komentar oleh {self.member_id} pada {self.content_id}"

    class Meta:
        verbose_name = "Komentar"
        verbose_name_plural = "Komentar"


class Progress(models.Model):
    member = models.ForeignKey(
        CourseMember,
        verbose_name="anggota",
        on_delete=models.CASCADE,
        related_name="progress"
    )
    content = models.ForeignKey(
        CourseContent,
        verbose_name="konten",
        on_delete=models.CASCADE,
        related_name="progress"
    )
    is_completed = models.BooleanField("selesai", default=False)
    completed_at = models.DateTimeField("waktu selesai", null=True, blank=True)

    def __str__(self):
        status = "selesai" if self.is_completed else "belum selesai"
        return f"{self.member.user_id.username} - {self.content.name} ({status})"

    class Meta:
        verbose_name = "Progress"
        verbose_name_plural = "Progress"
        unique_together = ('member', 'content')