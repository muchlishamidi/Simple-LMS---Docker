from ninja import Schema, Field
from datetime import datetime
from typing import Optional, List
from enum import Enum


# ── Sorting Enum (Chapter 8) ──────────────────────────────────
# Nilai positif = ascending, nilai dengan prefix "-" = descending.

class CourseOrdering(str, Enum):
    name_asc       = "name"
    name_desc      = "-name"
    price_asc      = "price"
    price_desc     = "-price"
    created_asc    = "created_at"
    created_desc   = "-created_at"


# ── User & Auth Schemas ───────────────────────────────────────
# Catatan: schema login & refresh token TIDAK didefinisikan di sini.
# Endpoint /auth/sign-in dan /auth/token-refresh sudah disediakan
# langsung oleh library django-ninja-simple-jwt (mobile_auth_router).

class UserOut(Schema):
    id: int
    username: str
    first_name: str
    last_name: str
    email: str
    role: str


class RegisterIn(Schema):
    username: str
    password: str
    email: str
    first_name: str = ''
    last_name: str = ''
    role: str = 'student'


class UpdateProfileIn(Schema):
    first_name: str = ''
    last_name: str = ''
    email: str = ''


# ── Category Schemas ──────────────────────────────────────────

class CategoryOut(Schema):
    id: int
    name: str
    parent_id: Optional[int] = None


# ── Course Schemas ────────────────────────────────────────────

class CourseIn(Schema):
    name: str
    description: str = '-'
    price: int = 10000


class CoursePatchIn(Schema):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[int] = None


class CourseOut(Schema):
    id: int
    name: str
    description: str
    price: int
    image: Optional[str] = ''
    teacher: UserOut
    category: Optional[CategoryOut] = None
    created_at: datetime
    updated_at: datetime


class ContentOut(Schema):
    id: int
    name: str
    order: int


class DetailCourseOut(CourseOut):
    contents: List[ContentOut] = Field(..., alias='coursecontent_set')


class PaginatedCourseOut(Schema):
    total: int
    page: int
    page_size: int
    total_pages: int
    results: List[CourseOut]


# ── Enrollment Schemas ────────────────────────────────────────

class EnrollmentIn(Schema):
    course_id: int


class EnrollmentOut(Schema):
    id: int
    course_id: int
    roles: str


class MyCourseOut(Schema):
    id: int
    course: CourseOut = Field(..., alias='course_id')
    roles: str


# ── Progress Schemas ──────────────────────────────────────────

class ProgressIn(Schema):
    content_id: int
    is_completed: bool = True


class ProgressOut(Schema):
    id: int
    is_completed: bool
    completed_at: Optional[datetime] = None


# ── Comment Schemas ───────────────────────────────────────────
# Mengikuti contoh otorisasi di Chapter 7 Section 7.3-7.5.
# Catatan: model Comment kita memakai member_id (FK ke CourseMember),
# bukan user_id langsung seperti contoh modul, jadi pengecekan ownership
# di api.py menelusuri comment.member_id.user_id.

class CommentIn(Schema):
    comment: str
    content_id: int


class CommentUpdateIn(Schema):
    comment: str


class CommentOut(Schema):
    id: int
    comment: str
    content_id: int
    member_id: int


# ── Analytics Schemas (MongoDB) ───────────────────────────────

class PopularCourseOut(Schema):
    course_id: int
    total_views: int
    unique_user_count: int


class DailySummaryOut(Schema):
    date: str
    total_actions: int
    unique_user_count: int


class UserActivityOut(Schema):
    user_id: int
    actions_breakdown: dict
    total_actions: int
    recent_activities: List[dict]


# ── Celery Task / Report Schemas ──────────────────────────────

class TaskTriggeredOut(Schema):
    task_id: str
    status: str
    message: str


class TaskStatusOut(Schema):
    task_id: str
    status: str
    result: Optional[dict] = None
    message: Optional[str] = None